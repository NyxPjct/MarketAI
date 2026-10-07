from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path
from statistics import median
from typing import Any, Dict, Optional

from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles

from backend.services.fx import get_rate_to_brl
from backend.services.market import (
    filter_compatible_listings,
    split_price_outliers,
)
from backend.services.sources import (
    integration_configuration,
    search_ebay_live,
    search_google_shopping_live,
    search_mercado_livre_catalog,
    search_mercado_livre_live,
)
from backend.services.pricing import PricingInputs, build_pricing
from backend.services.vision import identify_product
from backend.logging_config import configure_logging
from backend.services.settings import (
    SECRET_KEYS,
    apply_saved_secrets_to_environment,
    data_dir,
    load_preferences,
    platform_info,
    save_preferences,
    save_secrets,
    secret_presence,
)
from backend.version import APP_CHANNEL, APP_NAME, APP_VERSION
from backend.services import cloud as cloud_service
from backend.services.settings import load_cloud_session, clear_cloud_session

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"
# No modo web, usa o .env na raiz do projeto. No desktop empacotado, o
# launcher define MARKETAI_ENV_PATH apontando para o .env ao lado do .exe.
ENV_PATH = Path(os.getenv("MARKETAI_ENV_PATH", str(BASE_DIR / ".env")))
load_dotenv(ENV_PATH)
apply_saved_secrets_to_environment()
logger = configure_logging()
logger.info("Starting %s v%s (%s)", APP_NAME, APP_VERSION, APP_CHANNEL)

app = FastAPI(title=APP_NAME, version=APP_VERSION)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"])
app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

ML_SITES = {
    "BR": ("MLB", "Mercado Livre Brasil"),
    "MX": ("MLM", "Mercado Libre México"),
    "AR": ("MLA", "Mercado Libre Argentina"),
}
EBAY_MARKETS = {
    "US": ("EBAY_US", "eBay Estados Unidos"),
    "FR": ("EBAY_FR", "eBay França"),
    "DE": ("EBAY_DE", "eBay Alemanha"),
    "GB": ("EBAY_GB", "eBay Reino Unido"),
}
GOOGLE_SHOPPING_COUNTRIES = {"BR", "US", "FR", "DE", "GB", "MX", "AR", "CA", "JP", "KR"}
MIN_PRICING_LISTINGS = 3


def marketplace_breakdown(listings):
    groups = defaultdict(list)
    for item in listings:
        groups[item.get("source", "Outro")].append(float(item.get("price_brl", 0)))
    out = []
    for source, vals in groups.items():
        vals = [v for v in vals if v > 0]
        if not vals:
            continue
        out.append({
            "source": source,
            "count": len(vals),
            "min": round(min(vals), 2),
            "median": round(median(vals), 2),
            "average": round(sum(vals) / len(vals), 2),
            "max": round(max(vals), 2),
        })
    return sorted(out, key=lambda x: (-x["count"], x["median"]))


def _dedupe_listings(listings):
    seen = set()
    out = []
    for item in listings:
        key = (
            item.get("source", ""),
            item.get("url") or "",
            str(item.get("title", "")).lower(),
            round(float(item.get("price", 0)), 2),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def market_quality(state: str, raw_count: int, matched_count: int, pricing_count: int, ambiguity_blockers=None, avg_match=0, live_sources=0):
    ambiguity_blockers = ambiguity_blockers or []
    if state == "reliable":
        if pricing_count >= 8 and avg_match >= 82 and live_sources >= 2:
            confidence = "alta"
        elif pricing_count >= 5 and avg_match >= 75:
            confidence = "boa"
        else:
            confidence = "moderada"
        return {
            "state": state,
            "label": "Amostra compatível para cálculo",
            "message": f"{pricing_count} anúncios compatíveis passaram pelos filtros de variante e preço. Confiança de mercado: {confidence}.",
            "confidence": confidence,
            "blockers": [],
            "minimum_required": MIN_PRICING_LISTINGS,
            "average_match_score": round(avg_match, 1),
        }
    if state == "ambiguous":
        return {
            "state": state,
            "confidence": "bloqueada",
            "label": "Produto ambíguo",
            "message": "Encontrei anúncios reais, mas eles representam variantes diferentes. Não vou misturá-los em uma única mediana.",
            "blockers": ambiguity_blockers,
            "minimum_required": MIN_PRICING_LISTINGS,
            "average_match_score": round(avg_match, 1),
        }
    if state == "insufficient":
        return {
            "state": state,
            "confidence": "baixa",
            "label": "Amostra insuficiente",
            "message": f"Só {pricing_count or matched_count} anúncio(s) compatível(is) ficou(aram) disponível(is). São necessários pelo menos {MIN_PRICING_LISTINGS} para recomendar preço.",
            "blockers": ["Refine nome/variante ou conecte mais fontes de mercado."],
            "minimum_required": MIN_PRICING_LISTINGS,
            "average_match_score": round(avg_match, 1),
        }
    if state == "no_match":
        return {
            "state": state,
            "confidence": "indisponível",
            "label": "Nenhum anúncio compatível",
            "message": f"Foram encontrados {raw_count} anúncio(s), mas nenhum passou pelo filtro de produto/variante.",
            "blockers": ["Confira marca, modelo, volume/capacidade e variante."],
            "minimum_required": MIN_PRICING_LISTINGS,
            "average_match_score": 0,
        }
    return {
        "state": "unavailable",
        "confidence": "indisponível",
        "label": "Sem dados reais de mercado",
        "message": "Nenhuma fonte retornou anúncios reais nesta análise. O MarketAI não vai inventar uma faixa de mercado.",
        "blockers": ["Conecte uma integração compatível ou tente novamente quando a fonte estiver disponível."],
        "minimum_required": MIN_PRICING_LISTINGS,
        "average_match_score": 0,
    }


def commercial_advice(pricing, quality):
    state = quality["state"]
    minimum = pricing["costs"]["minimum_for_target_margin"]

    if state != "reliable":
        reasons = [f"Seu preço mínimo para atingir a margem desejada, considerando apenas os custos informados, é R$ {minimum:,.2f}.".replace(",", "X").replace(".", ",").replace("X", ".")]
        risks = list(quality.get("blockers") or [])
        risks.append("Sem mercado confiável, qualquer preço de venda seria apenas uma simulação de custos — não uma recomendação de mercado.")
        return {
            "verdict": "DADOS DE MERCADO INSUFICIENTES",
            "summary": quality["message"],
            "reasons": reasons[:4],
            "risks": risks[:4],
        }

    score = pricing["opportunity"]["score"]
    rec = pricing["strategies"]["recommended"]
    median_price = pricing["market"]["median"]
    reasons, risks = [], []

    if rec["net_margin_percent"] >= pricing["costs"]["desired_margin_percent"]:
        reasons.append(f"O preço recomendado preserva a margem desejada de {pricing['costs']['desired_margin_percent']:.1f}%.")
    else:
        risks.append("A margem recomendada ficou abaixo da meta informada.")
    if median_price > minimum * 1.08:
        reasons.append("A mediana dos anúncios compatíveis está confortavelmente acima do preço mínimo da sua meta.")
    elif median_price and median_price < minimum:
        risks.append("A mediana do mercado está abaixo do preço necessário para atingir sua margem desejada.")
    if pricing["market"]["count"] >= 10:
        reasons.append("A amostra tem boa quantidade de anúncios compatíveis.")
    else:
        risks.append("A amostra ainda é relativamente pequena; acompanhe novas referências antes de formar estoque grande.")

    if score >= 80:
        verdict = "VALE MUITO A PENA ANALISAR A COMPRA"
        summary = "Há boa folga entre custo, preço mínimo e o mercado compatível encontrado."
    elif score >= 65:
        verdict = "VALE A PENA"
        summary = "A relação entre margem e mercado está saudável, respeitando a variante identificada."
    elif score >= 45:
        verdict = "VALE COM CAUTELA"
        summary = "A operação pode funcionar, mas a margem ou a distância para os concorrentes exige controle maior."
    else:
        verdict = "NÃO ENTRARIA AGORA"
        summary = "A margem está apertada para o mercado compatível encontrado."
    return {"verdict": verdict, "summary": summary, "reasons": reasons[:4], "risks": risks[:4]}


@app.get("/")
async def home():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/health")
async def health():
    cfg = {x["id"]: x for x in integration_configuration()}
    configured_market = [k for k in ("mercadolivre", "ebay", "google_shopping") if cfg.get(k, {}).get("configured")]
    return {
        "ok": True,
        "version": APP_VERSION,
        "mode": "live_ready" if configured_market else "needs_market_credentials",
        "integrations": {
            "mercadolivre_token": cfg["mercadolivre"]["configured"],
            "ebay": cfg["ebay"]["configured"],
            "google_shopping": cfg["google_shopping"]["configured"],
            "vision": cfg["vision"]["configured"],
            "bcb": True,
        },
    }


@app.get("/api/integrations/status")
async def integrations_status():
    return {"version": APP_VERSION, "integrations": integration_configuration()}


@app.get("/api/integrations/test")
async def integrations_test(source: str = Query(...)):
    source = source.strip().lower()
    if source == "mercadolivre":
        result = await search_mercado_livre_live("Apple iPhone 16 128 GB", site="MLB", source_name="Mercado Livre Brasil")
        return result["diagnostic"]
    if source == "ebay":
        result = await search_ebay_live("Apple iPhone 16 128 GB", marketplace="EBAY_US", source_name="eBay Estados Unidos")
        return result["diagnostic"]
    if source == "google_shopping":
        result = await search_google_shopping_live("Apple iPhone 16 128 GB", country="BR")
        return result["diagnostic"]
    if source == "bcb":
        rate = await get_rate_to_brl("USD")
        return {
            "source": "Banco Central — PTAX", "source_id": "bcb", "configured": True,
            "auth": "public", "status": "ok" if rate.get("live") else "fallback",
            "returned": 1, "error": "" if rate.get("live") else "PTAX indisponível; foi usada taxa de contingência.",
            "latency_ms": 0, "checked_at": datetime.now(timezone.utc).isoformat(), "rate": rate,
        }
    if source == "vision":
        configured = bool(os.getenv("OPENAI_API_KEY", "").strip())
        return {
            "source": "Visão por IA", "source_id": "vision", "configured": configured,
            "auth": "api_key", "status": "configured" if configured else "not_configured",
            "returned": 0, "error": "" if configured else "Configure OPENAI_API_KEY.",
            "latency_ms": 0, "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    return {"source_id": source, "status": "unknown_source", "error": "Integração desconhecida."}


@app.get("/api/app/info")
async def app_info():
    prefs = load_preferences()
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "channel": APP_CHANNEL,
        "platform": platform_info(),
        "preferences": prefs,
        "privacy": {
            "local_data": True,
            "secrets_encrypted": os.name == "nt",
            "telemetry": False,
        },
    }


@app.get("/api/setup/status")
async def setup_status():
    prefs = load_preferences()
    presence = secret_presence()
    market_ready = bool(
        presence.get("MERCADOLIVRE_ACCESS_TOKEN")
        or (presence.get("EBAY_CLIENT_ID") and presence.get("EBAY_CLIENT_SECRET"))
        or presence.get("SERPAPI_KEY")
    )
    return {
        "version": APP_VERSION,
        "first_run_completed": bool(prefs.get("first_run_completed")),
        "market_source_configured": market_ready,
        "vision_configured": bool(presence.get("OPENAI_API_KEY")),
        "preferences": prefs,
    }


@app.get("/api/settings")
async def settings_get():
    return {
        "version": APP_VERSION,
        "preferences": load_preferences(),
        "credentials": secret_presence(),
        "storage": platform_info(),
    }


@app.post("/api/settings/integrations")
async def settings_integrations(payload: Dict[str, Any] = Body(default={})):
    values = payload.get("values") or {}
    clear = payload.get("clear") or []
    allowed = {k: values.get(k, "") for k in SECRET_KEYS if k in values}
    presence = save_secrets(allowed, [str(x) for x in clear])
    logger.info("Integration credentials updated: %s", {k: v for k, v in presence.items()})
    return {"ok": True, "credentials": presence, "integrations": integration_configuration()}


@app.post("/api/settings/preferences")
async def settings_preferences(payload: Dict[str, Any] = Body(default={})):
    prefs = save_preferences(payload)
    return {"ok": True, "preferences": prefs}


@app.post("/api/setup/complete")
async def setup_complete(payload: Dict[str, Any] = Body(default={})): 
    prefs_payload = dict(payload.get("preferences") or {})
    prefs_payload["first_run_completed"] = True
    prefs = save_preferences(prefs_payload)
    values = payload.get("credentials") or {}
    if values:
        save_secrets({k: values.get(k, "") for k in SECRET_KEYS if k in values})
    return {"ok": True, "preferences": prefs, "credentials": secret_presence()}


@app.post("/api/app/open-data-folder")
async def open_data_folder():
    path = data_dir()
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
            return {"ok": True, "path": str(path)}
        return {"ok": False, "path": str(path), "message": "Disponível no aplicativo Windows."}
    except Exception as exc:
        logger.exception("Could not open data directory")
        return JSONResponse(status_code=500, content={"ok": False, "message": str(exc)})


@app.get("/api/app/diagnostics")
async def app_diagnostics():
    cfg = integration_configuration()
    return {
        "app": {"name": APP_NAME, "version": APP_VERSION, "channel": APP_CHANNEL},
        "platform": platform_info(),
        "preferences": load_preferences(),
        "integrations": [{k: v for k, v in item.items() if k not in {"secret", "token"}} for item in cfg],
        "health": await health(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled API error on %s", getattr(request, "url", "unknown"))
    return JSONResponse(status_code=500, content={"detail": "O MarketAI encontrou um erro interno. Consulte os logs na pasta de dados."})


@app.post("/api/analyze/local")
async def analyze_local(
    product_name: str = Form(...),
    variant_text: str = Form(""),
    match_mode: str = Form("strict"),
    origin_country: str = Form("CN"),
    destination_country: str = Form("BR"),
    purchase_cost: float = Form(0),
    purchase_currency: str = Form("BRL"),
    quantity: int = Form(1),
    freight_total: float = Form(0),
    import_cost_total: float = Form(0),
    packaging_unit: float = Form(0),
    other_costs_unit: float = Form(0),
    marketplace_fee_percent: float = Form(16),
    taxes_percent: float = Form(6),
    ads_percent: float = Form(3),
    desired_margin_percent: float = Form(20),
    gtin: str = Form(""),
    ncm: str = Form(""),
    supplier_name: str = Form(""),
    national_reference_cost: float = Form(0),
    image: Optional[UploadFile] = File(None),
):
    if os.getenv("MARKETAI_DEVELOPER_MODE", "0").strip() != "1":
        return JSONResponse(status_code=403, content={"detail":"local_engine_disabled_in_commercial_release"})
    quantity = max(1, quantity)
    strict = match_mode != "balanced"
    image_bytes = await image.read() if image else None
    identity = await identify_product(product_name, variant_text, image_bytes, image.content_type if image else None)
    if gtin.strip():
        identity["gtin"] = gtin.strip()

    fx = await get_rate_to_brl(purchase_currency)
    purchase_cost_brl = purchase_cost * float(fx["rate"])
    freight_unit_brl = (freight_total * float(fx["rate"])) / quantity
    import_unit_brl = (import_cost_total * float(fx["rate"])) / quantity

    query_parts = [
        str(identity.get("brand") or ""),
        str(identity.get("model") or "") if str(identity.get("model") or "").lower() not in {"a confirmar", "unknown"} else "",
        product_name,
        variant_text,
        str(identity.get("variant_summary") or ""),
    ]
    query = " ".join(dict.fromkeys(x.strip() for x in query_parts if x and x.strip())).strip()

    # Commercial LIVE MARKET: query all destination-market sources concurrently and keep
    # explicit diagnostics. A failing source never silently becomes simulated data.
    jobs = []
    catalog_job = None
    if destination_country in ML_SITES:
        site, source_name = ML_SITES[destination_country]
        jobs.append(search_mercado_livre_live(query, site=site, source_name=source_name))
        if os.getenv("MERCADOLIVRE_ACCESS_TOKEN", "").strip():
            catalog_job = search_mercado_livre_catalog(query, site=site)
    if destination_country in EBAY_MARKETS:
        marketplace, source_name = EBAY_MARKETS[destination_country]
        jobs.append(search_ebay_live(query, marketplace=marketplace, source_name=source_name, gtin=gtin.strip()))
    if destination_country in GOOGLE_SHOPPING_COUNTRIES:
        jobs.append(search_google_shopping_live(query, country=destination_country))

    source_results = await asyncio.gather(*jobs) if jobs else []
    catalog_result = await catalog_job if catalog_job else {"items": [], "diagnostic": None}
    raw = []
    attempted_sources = []
    for result_source in source_results:
        raw.extend(result_source.get("items") or [])
        diag = dict(result_source.get("diagnostic") or {})
        if diag:
            diag["kind"] = "local_market"
            attempted_sources.append(diag)

    # Important: we intentionally do not mix a foreign marketplace into the destination
    # market median. Google Shopping is localized using the selected destination country.
    successful_live_sources = sum(1 for x in attempted_sources if x.get("status") == "ok" and int(x.get("returned") or 0) > 0)
    raw = _dedupe_listings(raw)

    rate_cache = {"BRL": {"rate": 1.0, "source": "BRL", "live": True}}
    normalized = []
    for item in raw:
        currency = (item.get("currency") or "BRL").upper()
        if currency not in rate_cache:
            rate_cache[currency] = await get_rate_to_brl(currency)
        x = dict(item)
        x["price_brl"] = round(float(item["price"]) * float(rate_cache[currency]["rate"]), 2)
        normalized.append(x)

    compatible, rejected_match, ambiguity = filter_compatible_listings(
        normalized,
        identity,
        product_name,
        variant_text=variant_text,
        gtin=gtin.strip(),
        strict=strict,
    )
    avg_match = sum(x.get("match_score", 0) for x in compatible) / len(compatible) if compatible else 0

    clean, rejected_outliers = split_price_outliers(compatible)
    rejected = rejected_match + rejected_outliers

    if not normalized:
        state = "unavailable"
    elif not compatible:
        state = "no_match"
    elif ambiguity.get("ambiguous"):
        state = "ambiguous"
    elif len(clean) < MIN_PRICING_LISTINGS:
        state = "insufficient"
    else:
        state = "reliable"

    quality = market_quality(
        state,
        raw_count=len(normalized),
        matched_count=len(compatible),
        pricing_count=len(clean),
        ambiguity_blockers=ambiguity.get("blockers"),
        avg_match=avg_match,
        live_sources=successful_live_sources,
    )

    pricing_inputs = PricingInputs(
        purchase_cost_brl=purchase_cost_brl,
        freight_brl=freight_unit_brl,
        import_cost_brl=import_unit_brl,
        packaging_brl=packaging_unit,
        other_costs_brl=other_costs_unit,
        marketplace_fee_percent=marketplace_fee_percent,
        taxes_percent=taxes_percent,
        ads_percent=ads_percent,
        desired_margin_percent=desired_margin_percent,
    )
    pricing_prices = [x["price_brl"] for x in clean] if state == "reliable" else []
    pricing = build_pricing(pricing_prices, pricing_inputs)
    advice = commercial_advice(pricing, quality)
    if purchase_currency.upper() != "BRL" and not fx.get("live"):
        advice["risks"] = (advice.get("risks") or [])[:3] + ["A cotação cambial usada é de contingência, não uma PTAX ao vivo. Valide o câmbio antes de fechar a compra."]

    landed = pricing["costs"]["unit_cost"]
    comparison = None
    if national_reference_cost > 0:
        diff = round(national_reference_cost - landed, 2)
        comparison = {
            "national_reference_cost": round(national_reference_cost, 2),
            "landed_import_cost": landed,
            "difference": diff,
            "cheaper_option": "importado" if diff > 0 else "nacional",
            "difference_percent": round(abs(diff) / national_reference_cost * 100, 2) if national_reference_cost else 0,
        }

    source_counts = defaultdict(int)
    merchants = set()
    for item in normalized:
        source_counts[item.get("source", "Outro")] += 1
        meta = item.get("metadata") or {}
        merchant = meta.get("merchant") or meta.get("official_store_name") or meta.get("seller_nickname") or meta.get("seller_username")
        if merchant:
            merchants.add(str(merchant))
    for item in attempted_sources:
        # The adapter's returned count is authoritative, but keep this fallback for older adapters.
        item["returned"] = int(item.get("returned") or source_counts.get(item.get("source", ""), 0))

    live_source_count = successful_live_sources
    checked_at = datetime.now(timezone.utc).isoformat()

    display_listings = clean if state == "reliable" else compatible
    display_listings = sorted(display_listings, key=lambda x: (-x.get("match_score", 0), x.get("price_brl", 0)))[:40]
    for x in display_listings:
        x["used_for_pricing"] = state == "reliable" and x in clean

    rejected = sorted(rejected, key=lambda x: (-x.get("match_score", 0), x.get("price_brl", 0)))[:60]

    return {
        "product": identity,
        "request": {
            "typed_name": product_name,
            "variant_text": variant_text.strip(),
            "match_mode": match_mode,
            "origin_country": origin_country,
            "destination_country": destination_country,
            "purchase_cost": purchase_cost,
            "purchase_currency": purchase_currency,
            "quantity": quantity,
            "gtin": gtin.strip() or identity.get("gtin"),
            "ncm": ncm.strip(),
            "supplier_name": supplier_name.strip(),
            "rates": {
                "marketplace_fee_percent": marketplace_fee_percent,
                "taxes_percent": taxes_percent,
                "ads_percent": ads_percent,
                "desired_margin_percent": desired_margin_percent,
            },
        },
        "fx": fx,
        "pricing": pricing,
        "advice": advice,
        "comparison": comparison,
        "market": {
            "live": live_source_count > 0,
            "reliable": state == "reliable",
            "checked_at": checked_at,
            "live_source_count": live_source_count,
            "merchant_count": len(merchants),
            "quality": quality,
            "raw_count": len(normalized),
            "matched_count": len(compatible),
            "pricing_count": len(clean) if state == "reliable" else 0,
            "discarded_count": len(rejected),
            "listings": display_listings,
            "discarded": rejected,
            "by_source": marketplace_breakdown(clean if state == "reliable" else compatible),
            "sources": attempted_sources,
            "query": query,
            "target_features": ambiguity.get("target_features") or {},
            "catalog_candidates": catalog_result.get("items") or [],
            "catalog_diagnostic": catalog_result.get("diagnostic"),
        },
        "notes": [
            "O MarketAI v0.0 comercial nunca fabrica anúncios ou uma mediana de mercado quando não há dados reais suficientes.",
            f"Uma recomendação de mercado só é liberada com pelo menos {MIN_PRICING_LISTINGS} anúncios compatíveis e sem ambiguidade crítica de variante.",
            "NCM e tributação real devem ser validados com contador/despachante.",
        ],
    }


@app.get("/api/radar")
async def radar_removed():
    return JSONResponse(
        status_code=410,
        content={
            "status": "disabled_in_commercial_release",
            "message": "O Radar demonstrativo foi removido da edição comercial. Ele retornará somente quando operar com fontes reais de fornecedores.",
        },
    )


# ===================== COMMERCIAL CLOUD CLIENT =====================
@app.get("/api/cloud/status")
async def cloud_status():
    return await cloud_service.account_status()

@app.post("/api/cloud/login")
async def cloud_login(payload: Dict[str, Any] = Body(...)):
    try:
        r=await cloud_service.login(str(payload.get("email") or ""),str(payload.get("password") or ""))
        return JSONResponse(status_code=r.status_code,content=r.json() if r.content else {"ok":r.is_success})
    except Exception as e:
        return JSONResponse(status_code=503,content={"detail":"cloud_unavailable","message":str(e)})

@app.post("/api/cloud/register")
async def cloud_register(payload: Dict[str, Any] = Body(...)):
    try:
        r=await cloud_service.register(str(payload.get("email") or ""),str(payload.get("password") or ""),str(payload.get("full_name") or ""))
        return JSONResponse(status_code=r.status_code,content=r.json() if r.content else {"ok":r.is_success})
    except Exception as e:
        return JSONResponse(status_code=503,content={"detail":"cloud_unavailable","message":str(e)})

@app.post("/api/cloud/logout")
async def cloud_logout():
    await cloud_service.logout(); return {"ok":True}

@app.get("/api/cloud/plans")
async def cloud_plans(country_code: str = "BR", currency: str = ""):
    try:
        q=f"/v1/plans?country_code={country_code}" + (f"&currency={currency}" if currency else "")
        r=await cloud_service.request("GET",q,auth=False); return JSONResponse(status_code=r.status_code,content=r.json())
    except Exception as e:
        return JSONResponse(status_code=503,content={"detail":"cloud_unavailable","message":str(e)})

@app.get("/api/cloud/payment-methods")
async def cloud_payment_methods(country_code: str = "BR"):
    try:
        r=await cloud_service.request("GET",f"/v1/billing/methods?country_code={country_code}",auth=False); return JSONResponse(status_code=r.status_code,content=r.json())
    except Exception as e:
        return JSONResponse(status_code=503,content={"detail":"cloud_unavailable","message":str(e)})

@app.post("/api/cloud/checkout")
async def cloud_checkout(payload: Dict[str, Any] = Body(...)):
    try:
        r=await cloud_service.request("POST","/v1/billing/checkout",json_data=payload); return JSONResponse(status_code=r.status_code,content=r.json())
    except Exception as e:
        return JSONResponse(status_code=503,content={"detail":"cloud_unavailable","message":str(e)})

@app.post("/api/cloud/license")
async def cloud_license(payload: Dict[str, Any] = Body(...)):
    try:
        r=await cloud_service.request("POST","/v1/licenses/activate",json_data=payload); return JSONResponse(status_code=r.status_code,content=r.json())
    except Exception as e:
        return JSONResponse(status_code=503,content={"detail":"cloud_unavailable","message":str(e)})

@app.get("/api/cloud/devices")
async def cloud_devices():
    try:
        r=await cloud_service.request("GET","/v1/devices"); return JSONResponse(status_code=r.status_code,content=r.json())
    except Exception as e:
        return JSONResponse(status_code=503,content={"detail":"cloud_unavailable","message":str(e)})

@app.delete("/api/cloud/devices/{device_id}")
async def cloud_remove_device(device_id: str):
    try:
        r=await cloud_service.request("DELETE",f"/v1/devices/{device_id}"); return JSONResponse(status_code=r.status_code,content=r.json())
    except Exception as e:
        return JSONResponse(status_code=503,content={"detail":"cloud_unavailable","message":str(e)})

@app.get("/api/update/check")
async def update_check():
    try:
        r=await cloud_service.request("GET","/v1/updates/latest",auth=False); return JSONResponse(status_code=r.status_code,content=r.json())
    except Exception as e:
        return {"available":False,"version":APP_VERSION,"error":str(e)}

@app.post("/api/analyze")
async def analyze_cloud(
    product_name: str = Form(...), variant_text: str = Form(""), match_mode: str = Form("strict"), origin_country: str = Form("CN"), destination_country: str = Form("BR"), purchase_cost: float = Form(0), purchase_currency: str = Form("BRL"), quantity: int = Form(1), freight_total: float = Form(0), import_cost_total: float = Form(0), packaging_unit: float = Form(0), other_costs_unit: float = Form(0), marketplace_fee_percent: float = Form(16), taxes_percent: float = Form(6), ads_percent: float = Form(3), desired_margin_percent: float = Form(20), gtin: str = Form(""), ncm: str = Form(""), supplier_name: str = Form(""), national_reference_cost: float = Form(0), image: Optional[UploadFile] = File(None),
):
    fields={"product_name":product_name,"variant_text":variant_text,"match_mode":match_mode,"origin_country":origin_country,"destination_country":destination_country,"purchase_cost":purchase_cost,"purchase_currency":purchase_currency,"quantity":quantity,"freight_total":freight_total,"import_cost_total":import_cost_total,"packaging_unit":packaging_unit,"other_costs_unit":other_costs_unit,"marketplace_fee_percent":marketplace_fee_percent,"taxes_percent":taxes_percent,"ads_percent":ads_percent,"desired_margin_percent":desired_margin_percent,"gtin":gtin,"ncm":ncm,"supplier_name":supplier_name,"national_reference_cost":national_reference_cost}
    files=None
    if image:
        content=await image.read(); files={"image":(image.filename or "product.jpg",content,image.content_type or "application/octet-stream")}
    try:
        r=await cloud_service.request("POST","/v1/analysis",data={k:str(v) for k,v in fields.items()},files=files)
        try: content=r.json()
        except Exception: content={"detail":r.text[:500]}
        return JSONResponse(status_code=r.status_code,content=content)
    except Exception as e:
        return JSONResponse(status_code=503,content={"detail":"cloud_unavailable","message":str(e)})


@app.post("/api/cloud/cancel-subscription")
async def cloud_cancel_subscription():
    try:
        r=await cloud_service.request("POST","/v1/billing/cancel",json_data={}); return JSONResponse(status_code=r.status_code,content=r.json())
    except Exception as e:
        return JSONResponse(status_code=503,content={"detail":"cloud_unavailable","message":str(e)})

@app.post("/api/app/open-url")
async def open_external_url(payload: Dict[str, Any] = Body(...)):
    import webbrowser
    url=str(payload.get("url") or "").strip()
    if not (url.startswith("https://") or url.startswith("http://127.0.0.1") or url.startswith("http://localhost")):
        return JSONResponse(status_code=400,content={"detail":"invalid_url"})
    return {"ok":bool(webbrowser.open(url))}

@app.post("/api/update/install")
async def update_install(payload: Dict[str, Any] = Body(...)):
    try:
        path=await cloud_service.download_update(payload)
        launched=cloud_service.launch_installer(path)
        return {"ok":launched,"path":str(path),"message":"Instalador iniciado." if launched else "Atualização baixada; instalação automática só está disponível no Windows."}
    except Exception as e:
        return JSONResponse(status_code=400,content={"detail":"update_failed","message":str(e)})


@app.post("/api/cloud/sync-subscription")
async def cloud_sync_subscription():
    try:
        r=await cloud_service.request("POST","/v1/billing/sync",json_data={}); return JSONResponse(status_code=r.status_code,content=r.json())
    except Exception as e:
        return JSONResponse(status_code=503,content={"detail":"cloud_unavailable","message":str(e)})

# ===================== MARKETAI INTELLIGENCE CORE =====================
async def _proxy_intelligence(method: str, path: str, payload=None):
    try:
        r=await cloud_service.request(method,path,json_data=payload)
        try: body=r.json()
        except Exception: body={"detail":r.text[:500]}
        return JSONResponse(status_code=r.status_code,content=body)
    except Exception as e:
        return JSONResponse(status_code=503,content={"detail":"cloud_unavailable","message":str(e)})

@app.get("/api/intelligence/capabilities")
async def intelligence_capabilities(): return await _proxy_intelligence("GET","/v1/intelligence/capabilities")
@app.post("/api/intelligence/profit")
async def intelligence_profit(payload: Dict[str,Any]=Body(...)): return await _proxy_intelligence("POST","/v1/intelligence/profit",payload)
@app.get("/api/intelligence/watches")
async def intelligence_watches(): return await _proxy_intelligence("GET","/v1/intelligence/watches")
@app.post("/api/intelligence/watches")
async def intelligence_watch_create(payload: Dict[str,Any]=Body(...)): return await _proxy_intelligence("POST","/v1/intelligence/watches",payload)
@app.delete("/api/intelligence/watches/{watch_id}")
async def intelligence_watch_delete(watch_id:str): return await _proxy_intelligence("DELETE",f"/v1/intelligence/watches/{watch_id}")
@app.post("/api/intelligence/watches/{watch_id}/check")
async def intelligence_watch_check(watch_id:str): return await _proxy_intelligence("POST",f"/v1/intelligence/watches/{watch_id}/check",{})
@app.get("/api/intelligence/watches/{watch_id}/history")
async def intelligence_watch_history(watch_id:str): return await _proxy_intelligence("GET",f"/v1/intelligence/watches/{watch_id}/history")
@app.get("/api/intelligence/radar")
async def intelligence_radar(): return await _proxy_intelligence("GET","/v1/intelligence/radar")
@app.get("/api/intelligence/alerts")
async def intelligence_alerts(): return await _proxy_intelligence("GET","/v1/intelligence/alerts")
@app.post("/api/intelligence/alerts/{alert_id}/ack")
async def intelligence_alert_ack(alert_id:str): return await _proxy_intelligence("POST",f"/v1/intelligence/alerts/{alert_id}/ack",{})
@app.get("/api/intelligence/forecast/{watch_id}")
async def intelligence_forecast(watch_id:str): return await _proxy_intelligence("GET",f"/v1/intelligence/forecast/{watch_id}")
@app.post("/api/intelligence/copilot")
async def intelligence_copilot(payload: Dict[str,Any]=Body(...)): return await _proxy_intelligence("POST","/v1/intelligence/copilot",payload)
