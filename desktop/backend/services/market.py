from __future__ import annotations

import base64
import os
import re
import unicodedata
from collections import Counter
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import httpx


GENERIC_WORDS = {
    "de", "da", "do", "das", "dos", "e", "a", "o", "as", "os", "para", "com", "sem",
    "the", "and", "for", "with", "new", "novo", "original", "produto", "unidade", "un",
    "masculino", "feminino", "men", "women", "homme", "femme",
}

DISALLOWED_VARIANTS = {
    "decant": ("decant", "decante"),
    "sample": ("amostra", "sample", "sachet"),
    "miniature": ("miniatura", "miniature", "mini"),
    "inspired": ("inspirado", "inspired", "contratipo", "similar ao"),
    "replica": ("replica", "fake", "falso"),
    "tester": ("tester", "testador"),
    "refill": ("refil", "refill", "recharge"),
    "kit": ("kit", "set", "gift set", "coffret"),
}

CONCENTRATIONS = [
    ("elixir", (r"\belixir\b",)),
    ("edp", (r"\beau\s+de\s+parfum\b", r"\bedp\b")),
    ("edt", (r"\beau\s+de\s+toilette\b", r"\bedt\b")),
    ("edc", (r"\beau\s+de\s+cologne\b", r"\bedc\b")),
    ("parfum", (r"\bparfum\b", r"\bperfume\b")),
]


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("–", "-").replace("—", "-")
    value = re.sub(r"[^a-z0-9.,+\-/ ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def significant_tokens(value: str) -> List[str]:
    tokens = []
    for token in re.findall(r"[a-z0-9]+", normalize_text(value)):
        if len(token) < 2 or token in GENERIC_WORDS:
            continue
        if token not in tokens:
            tokens.append(token)
    return tokens


def extract_features(value: str) -> Dict:
    text = normalize_text(value)
    features: Dict[str, object] = {}

    # Perfume concentration. More specific patterns are intentionally checked first.
    for name, patterns in CONCENTRATIONS:
        if any(re.search(pattern, text) for pattern in patterns):
            features["concentration"] = name
            break

    volumes: List[float] = []
    for m in re.finditer(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*ml\b", text):
        try:
            volumes.append(round(float(m.group(1).replace(",", ".")), 1))
        except ValueError:
            pass
    for m in re.finditer(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(?:fl\.?\s*oz|oz)\b", text):
        try:
            volumes.append(round(float(m.group(1).replace(",", ".")) * 29.5735, 1))
        except ValueError:
            pass
    if volumes:
        features["volume_ml"] = volumes[0]

    capacity = re.search(r"(?<!\d)(\d+(?:[.,]\d+)?)\s*(tb|gb)\b", text)
    if capacity:
        value_num = float(capacity.group(1).replace(",", "."))
        features["capacity_gb"] = int(round(value_num * (1024 if capacity.group(2) == "tb" else 1)))

    power = re.search(r"(?<!\d)(\d{2,5})\s*w(?:atts?)?\b", text)
    if power:
        features["power_w"] = int(power.group(1))

    for key, variants in DISALLOWED_VARIANTS.items():
        if any(re.search(rf"(?<![a-z0-9]){re.escape(v)}(?![a-z0-9])", text) for v in variants):
            features[key] = True

    return features


def _clean_listing(
    source: str,
    title: str,
    price: float,
    currency: str,
    url: str = "",
    condition: str = "Novo",
    metadata: Optional[Dict] = None,
) -> Dict:
    return {
        "source": source,
        "title": title,
        "price": round(float(price), 2),
        "currency": currency,
        "url": url,
        "condition": condition,
        "metadata": metadata or {},
    }


async def search_mercado_livre(query: str, site: str = "MLB", source_name: str = "Mercado Livre") -> List[Dict]:
    """Search active marketplace listings.

    Mercado Livre documents /sites/{site}/search as a public listings resource. If an
    access token is configured we send it; otherwise we still attempt the public request.
    This lets local installations use whatever public access the marketplace currently
    permits without ever fabricating results.
    """
    token = os.getenv("MERCADOLIVRE_ACCESS_TOKEN", "").strip()
    url = f"https://api.mercadolibre.com/sites/{site}/search?q={quote_plus(query)}&limit=50"
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            items = r.json().get("results", [])
        out = []
        for item in items:
            if not item.get("price"):
                continue
            attrs = {}
            for attr in item.get("attributes") or []:
                if attr.get("id") and (attr.get("value_name") or attr.get("value_id")):
                    attrs[attr["id"]] = attr.get("value_name") or attr.get("value_id")
            out.append(_clean_listing(
                source_name,
                item.get("title", query),
                item.get("price", 0),
                item.get("currency_id", "BRL"),
                item.get("permalink", ""),
                item.get("condition", "new"),
                {
                    "id": item.get("id"),
                    "catalog_product_id": item.get("catalog_product_id"),
                    "category_id": item.get("category_id"),
                    "attributes": attrs,
                },
            ))
        return out
    except Exception:
        return []


async def _ebay_token() -> Optional[str]:
    client_id = os.getenv("EBAY_CLIENT_ID", "").strip()
    client_secret = os.getenv("EBAY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        return None
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }
    try:
        async with httpx.AsyncClient(timeout=12) as client:
            r = await client.post("https://api.ebay.com/identity/v1/oauth2/token", headers=headers, data=data)
            r.raise_for_status()
            return r.json().get("access_token")
    except Exception:
        return None


async def search_ebay(
    query: str,
    marketplace: str = "EBAY_US",
    source_name: str = "eBay",
    gtin: str = "",
) -> List[Dict]:
    token = await _ebay_token()
    if not token:
        return []
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": marketplace,
    }
    params = ["limit=50", "filter=conditions:{NEW}"]
    if gtin.strip():
        params.append(f"gtin={quote_plus(gtin.strip())}")
    else:
        params.append(f"q={quote_plus(query)}")
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search?" + "&".join(params)
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            items = r.json().get("itemSummaries", [])
        out = []
        for item in items:
            p = item.get("price") or {}
            if not p.get("value"):
                continue
            out.append(_clean_listing(
                source_name,
                item.get("title", query),
                float(p.get("value")),
                p.get("currency", "USD"),
                item.get("itemWebUrl", ""),
                item.get("condition", "New"),
                {
                    "item_id": item.get("itemId"),
                    "epid": item.get("epid"),
                    "categories": item.get("categories") or [],
                },
            ))
        return out
    except Exception:
        return []


def _target_signature(identity: Dict, typed_name: str, variant_text: str = "", gtin: str = "") -> Dict:
    merged = " ".join([
        typed_name or "",
        variant_text or "",
        str(identity.get("variant") or ""),
        " ".join(str(x) for x in (identity.get("attributes") or [])),
    ])
    features = extract_features(merged)

    # Structured identity fields override text extraction when supplied by vision.
    for key in ("concentration", "volume_ml", "capacity_gb", "power_w"):
        if identity.get(key) not in (None, "", 0):
            try:
                features[key] = float(identity[key]) if key == "volume_ml" else identity[key]
            except (TypeError, ValueError):
                pass

    brand = normalize_text(identity.get("brand") or "")
    if brand in {"", "a confirmar", "nao identificada", "não identificada"}:
        brand = ""
    model = normalize_text(identity.get("model") or "")
    if model in {"", "a confirmar", "desconhecido", "unknown"}:
        model = ""

    query_tokens = significant_tokens(" ".join([typed_name, variant_text]))
    return {
        "brand": brand,
        "model": model,
        "tokens": query_tokens,
        "features": features,
        "gtin": re.sub(r"\D", "", gtin or str(identity.get("gtin") or "")),
    }


def evaluate_listing(
    listing: Dict,
    identity: Dict,
    typed_name: str,
    variant_text: str = "",
    gtin: str = "",
    strict: bool = True,
) -> Dict:
    item = dict(listing)
    title = normalize_text(item.get("title", ""))
    target = _target_signature(identity, typed_name, variant_text, gtin)
    target_features = target["features"]
    listing_features = extract_features(title)
    reasons: List[str] = []
    blockers: List[str] = []
    score = 35.0

    condition = normalize_text(item.get("condition", ""))
    if condition and any(x in condition for x in ("used", "usado", "refurb", "recondicionado")):
        blockers.append("condição diferente de novo")

    brand = target["brand"]
    if brand:
        if brand in title:
            score += 18
            reasons.append("marca confere")
        else:
            blockers.append("marca não confere no título")

    model_tokens = significant_tokens(target["model"])
    if model_tokens:
        model_hits = sum(1 for t in model_tokens if t in title)
        model_ratio = model_hits / max(1, len(model_tokens))
        score += model_ratio * 18
        if model_ratio < 0.5:
            blockers.append("modelo não confere")
        elif model_ratio >= 0.8:
            reasons.append("modelo confere")

    tokens = target["tokens"]
    if tokens:
        hits = sum(1 for t in tokens if t in title)
        ratio = hits / len(tokens)
        score += ratio * 25
        if ratio >= 0.8:
            reasons.append("nome altamente compatível")
        elif strict and ratio < 0.60:
            blockers.append("nome pouco compatível")

    # Reject formats that are commonly not comparable with a normal full product.
    for key, variants in DISALLOWED_VARIANTS.items():
        listing_has = bool(listing_features.get(key))
        target_has = bool(target_features.get(key))
        if listing_has and not target_has:
            labels = {
                "decant": "decant", "sample": "amostra", "miniature": "miniatura",
                "inspired": "inspirado/contratipo", "replica": "réplica",
                "tester": "tester", "refill": "refil", "kit": "kit/conjunto",
            }
            blockers.append(f"variante incompatível: {labels[key]}")

    target_conc = target_features.get("concentration")
    listing_conc = listing_features.get("concentration")
    if target_conc:
        if listing_conc and listing_conc != target_conc:
            blockers.append(f"concentração diferente ({listing_conc} ≠ {target_conc})")
        elif listing_conc == target_conc:
            score += 12
            reasons.append("concentração confere")
        else:
            score -= 7

    target_volume = target_features.get("volume_ml")
    listing_volume = listing_features.get("volume_ml")
    if target_volume:
        try:
            tv = float(target_volume)
            if listing_volume is not None:
                lv = float(listing_volume)
                tolerance = max(2.0, tv * 0.03)
                if abs(lv - tv) > tolerance:
                    blockers.append(f"volume diferente ({lv:g} ml ≠ {tv:g} ml)")
                else:
                    score += 12
                    reasons.append("volume confere")
            else:
                score -= 7
        except (TypeError, ValueError):
            pass

    for key, label, tolerance in (
        ("capacity_gb", "capacidade", 0),
        ("power_w", "potência", 0.03),
    ):
        target_val = target_features.get(key)
        list_val = listing_features.get(key)
        if target_val:
            if list_val is not None:
                tv = float(target_val)
                lv = float(list_val)
                is_mismatch = abs(lv - tv) > (max(1.0, tv * tolerance) if tolerance else 0.1)
                if is_mismatch:
                    blockers.append(f"{label} diferente ({list_val} ≠ {target_val})")
                else:
                    score += 8
                    reasons.append(f"{label} confere")
            else:
                score -= 4

    score = max(0, min(100, int(round(score))))
    threshold = 67 if strict else 52
    if score < threshold and not blockers:
        blockers.append(f"compatibilidade baixa ({score}%)")

    item["features"] = listing_features
    item["match_score"] = score
    item["match_reasons"] = reasons[:5]
    item["rejection_reason"] = "; ".join(dict.fromkeys(blockers)) if blockers else ""
    item["compatible"] = not blockers
    return item


def filter_compatible_listings(
    listings: List[Dict],
    identity: Dict,
    typed_name: str,
    variant_text: str = "",
    gtin: str = "",
    strict: bool = True,
) -> Tuple[List[Dict], List[Dict], Dict]:
    accepted: List[Dict] = []
    rejected: List[Dict] = []
    for listing in listings:
        scored = evaluate_listing(listing, identity, typed_name, variant_text, gtin, strict)
        (accepted if scored["compatible"] else rejected).append(scored)

    target = _target_signature(identity, typed_name, variant_text, gtin)
    target_features = target["features"]
    blockers: List[str] = []

    concentrations = Counter(
        x.get("features", {}).get("concentration") for x in accepted if x.get("features", {}).get("concentration")
    )
    if not target_features.get("concentration") and len(concentrations) >= 2:
        labels = ", ".join(f"{k.upper()} ({v})" for k, v in concentrations.most_common(4))
        blockers.append(f"Há concentrações diferentes entre os anúncios: {labels}. Informe a concentração exata.")

    volumes = Counter(
        round(float(x.get("features", {}).get("volume_ml")), 1)
        for x in accepted if x.get("features", {}).get("volume_ml") is not None
    )
    if not target_features.get("volume_ml") and len(volumes) >= 2:
        labels = ", ".join(f"{k:g} ml ({v})" for k, v in volumes.most_common(5))
        blockers.append(f"Há volumes diferentes entre os anúncios: {labels}. Informe o volume/tamanho exato.")

    capacities = Counter(
        int(x.get("features", {}).get("capacity_gb"))
        for x in accepted if x.get("features", {}).get("capacity_gb") is not None
    )
    if not target_features.get("capacity_gb") and len(capacities) >= 2:
        labels = ", ".join(f"{k} GB ({v})" for k, v in capacities.most_common(5))
        blockers.append(f"Há capacidades diferentes entre os anúncios: {labels}. Informe a capacidade exata.")

    powers = Counter(
        int(x.get("features", {}).get("power_w"))
        for x in accepted if x.get("features", {}).get("power_w") is not None
    )
    if not target_features.get("power_w") and len(powers) >= 2:
        labels = ", ".join(f"{k} W ({v})" for k, v in powers.most_common(5))
        blockers.append(f"Há potências diferentes entre os anúncios: {labels}. Informe a potência exata.")

    return accepted, rejected, {
        "ambiguous": bool(blockers),
        "blockers": blockers,
        "target_features": target_features,
    }


def split_price_outliers(listings: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
    vals = sorted([float(x["price_brl"]) for x in listings if x.get("price_brl", 0) > 0])
    if len(vals) < 5:
        return listings, []
    q1 = vals[len(vals) // 4]
    q3 = vals[(len(vals) * 3) // 4]
    iqr = q3 - q1
    lo = max(0, q1 - 1.5 * iqr)
    hi = q3 + 1.5 * iqr
    accepted, rejected = [], []
    for item in listings:
        price = float(item.get("price_brl", 0))
        if lo <= price <= hi:
            accepted.append(item)
        else:
            x = dict(item)
            x["compatible"] = False
            x["rejection_reason"] = f"preço fora da faixa estatística ({lo:.2f}–{hi:.2f})"
            rejected.append(x)
    return accepted, rejected


def remove_price_outliers(listings: List[Dict]) -> List[Dict]:
    """Backward-compatible wrapper for v0.2 callers/tests."""
    return split_price_outliers(listings)[0]
