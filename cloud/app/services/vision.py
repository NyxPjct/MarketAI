from __future__ import annotations

import base64
import json
import os
import re
from typing import Dict, Optional

import httpx

from app.services.market import extract_features


def _variant_summary(data: Dict) -> str:
    parts = []
    conc = data.get("concentration")
    if conc:
        parts.append(str(conc).upper())
    if data.get("volume_ml"):
        parts.append(f"{float(data['volume_ml']):g} ml")
    if data.get("capacity_gb"):
        parts.append(f"{int(data['capacity_gb'])} GB")
    if data.get("power_w"):
        parts.append(f"{int(data['power_w'])} W")
    if data.get("variant"):
        parts.append(str(data["variant"]))
    # preserve order while removing duplicates
    return " · ".join(dict.fromkeys(x for x in parts if x))


def fallback_identity(name: str, variant_text: str = "") -> Dict:
    tokens = [x for x in re.split(r"\s+", name.strip()) if x]
    brand = tokens[0] if tokens else "Não identificada"
    features = extract_features(f"{name} {variant_text}")
    result = {
        "product_name": name.strip() or "Produto não informado",
        "brand": brand,
        "model": "A confirmar",
        "category": "A confirmar",
        "variant": variant_text.strip() or None,
        "gtin": None,
        "attributes": [variant_text.strip()] if variant_text.strip() else [],
        "confidence": 55,
        "mode": "name_fallback",
    }
    result.update({k: v for k, v in features.items() if k in {"concentration", "volume_ml", "capacity_gb", "power_w"}})
    result["variant_summary"] = _variant_summary(result)
    return result


async def identify_product(name: str, variant_text: str, image_bytes: Optional[bytes], content_type: Optional[str]) -> Dict:
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("OPENAI_VISION_MODEL", "gpt-6-luna")
    if not api_key or not image_bytes:
        return fallback_identity(name, variant_text)

    mime = content_type or "image/jpeg"
    b64 = base64.b64encode(image_bytes).decode()
    data_url = f"data:{mime};base64,{b64}"

    prompt = (
        "Identify the exact retail product and variant in this image. The result will be used to compare market listings, "
        "so variant precision matters more than guessing. Use the typed name and variant as hints, but never invent details. "
        "Return ONLY compact JSON with keys: product_name, brand, model, category, variant, concentration "
        "(one of edp/edt/edc/parfum/elixir or null), volume_ml (number or null), capacity_gb (number or null), "
        "power_w (number or null), gtin (string or null), attributes (array of short strings), confidence (0-100). "
        f"Typed name: {name or 'not provided'}. Typed variant/details: {variant_text or 'not provided'}"
    )
    payload = {
        "model": model,
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": prompt},
                {"type": "input_image", "image_url": data_url},
            ],
        }],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post("https://api.openai.com/v1/responses", headers=headers, json=payload)
            r.raise_for_status()
            body = r.json()
        text = body.get("output_text")
        if not text:
            chunks = []
            for item in body.get("output", []):
                for c in item.get("content", []):
                    if c.get("type") in ("output_text", "text") and c.get("text"):
                        chunks.append(c["text"])
            text = "\n".join(chunks)
        if text:
            text = text.strip().strip("`")
            if text.startswith("json"):
                text = text[4:].strip()
            result = json.loads(text)
            # Typed detail wins over missing visual detail, never over a confident visual value.
            typed_features = extract_features(f"{name} {variant_text}")
            for key in ("concentration", "volume_ml", "capacity_gb", "power_w"):
                if result.get(key) in (None, "", 0) and typed_features.get(key) is not None:
                    result[key] = typed_features[key]
            result["mode"] = "ai_vision"
            result["variant_summary"] = _variant_summary(result)
            return result
    except Exception:
        pass

    return fallback_identity(name, variant_text)
