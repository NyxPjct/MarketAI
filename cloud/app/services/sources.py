from __future__ import annotations

import base64
import os
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import httpx

from app.services.market import _clean_listing

DEFAULT_TIMEOUT = float(os.getenv("HTTP_TIMEOUT", "12"))

SERP_COUNTRY = {
    "BR": ("br", "pt-BR", "BRL"),
    "US": ("us", "en", "USD"),
    "FR": ("fr", "fr", "EUR"),
    "DE": ("de", "de", "EUR"),
    "GB": ("uk", "en", "GBP"),
    "MX": ("mx", "es", "MXN"),
    "AR": ("ar", "es", "ARS"),
    "CA": ("ca", "en", "CAD"),
    "JP": ("jp", "ja", "JPY"),
    "KR": ("kr", "ko", "KRW"),
}

_EBAY_TOKEN_CACHE: Dict[str, object] = {"token": None, "expires_at": 0.0, "client_id": None}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_error(response: Optional[httpx.Response], fallback: str) -> str:
    if response is None:
        return fallback
    try:
        body = response.json()
        for key in ("message", "error_description", "error", "detail"):
            if body.get(key):
                return str(body[key])[:260]
    except Exception:
        pass
    text = (response.text or "").strip().replace("\n", " ")
    return (text[:260] if text else fallback)


def _status_for_http(code: int) -> str:
    if code in (401, 403):
        return "auth_required"
    if code == 429:
        return "rate_limited"
    if 500 <= code:
        return "upstream_error"
    return "http_error"


def _diag(source: str, source_id: str, configured: bool, auth_mode: str, status: str,
          returned: int = 0, error: str = "", latency_ms: int = 0, **extra) -> Dict:
    data = {
        "source": source,
        "source_id": source_id,
        "configured": configured,
        "auth": auth_mode,
        "status": status,
        "returned": returned,
        "error": error,
        "latency_ms": latency_ms,
        "checked_at": now_iso(),
    }
    data.update(extra)
    return data


async def search_mercado_livre_live(query: str, site: str = "MLB", source_name: str = "Mercado Livre") -> Dict:
    """Search real Mercado Livre listings and return transparent diagnostics.

    The app never fabricates data when this source fails. A token is preferred; when it is
    absent, a public request is attempted because availability can vary by resource/site.
    """
    token = os.getenv("MERCADOLIVRE_ACCESS_TOKEN", "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    params = {"q": query, "limit": 50}
    url = f"https://api.mercadolibre.com/sites/{site}/search"
    started = time.perf_counter()
    response: Optional[httpx.Response] = None
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url, headers=headers, params=params)
        latency = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            if response.status_code in (401, 403) and not token:
                error = "A busca deste site exige autenticação. Configure MERCADOLIVRE_ACCESS_TOKEN."
            elif response.status_code in (401, 403):
                error = "Access token do Mercado Livre inválido, expirado ou sem permissão para esta consulta."
            else:
                error = _safe_error(response, f"HTTP {response.status_code}")
            return {"items": [], "diagnostic": _diag(source_name, "mercadolivre", bool(token), "access_token" if token else "public_attempt", _status_for_http(response.status_code), error=error, latency_ms=latency, http_status=response.status_code)}

        payload = response.json()
        items = payload.get("results", [])
        out: List[Dict] = []
        for item in items:
            if item.get("price") in (None, 0, "0"):
                continue
            attrs = {}
            for attr in item.get("attributes") or []:
                if attr.get("id") and (attr.get("value_name") or attr.get("value_id")):
                    attrs[attr["id"]] = attr.get("value_name") or attr.get("value_id")
            seller = item.get("seller") or {}
            shipping = item.get("shipping") or {}
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
                    "seller_id": seller.get("id"),
                    "seller_nickname": seller.get("nickname"),
                    "official_store_name": item.get("official_store_name"),
                    "free_shipping": shipping.get("free_shipping"),
                    "available_quantity": item.get("available_quantity"),
                },
            ))
        return {
            "items": out,
            "diagnostic": _diag(source_name, "mercadolivre", bool(token), "access_token" if token else "public_attempt", "ok", returned=len(out), latency_ms=latency, http_status=response.status_code, paging=payload.get("paging") or {}),
        }
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return {"items": [], "diagnostic": _diag(source_name, "mercadolivre", bool(token), "access_token" if token else "public_attempt", "network_error", error=str(exc)[:260], latency_ms=latency)}


async def search_mercado_livre_catalog(query: str, site: str = "MLB") -> Dict:
    token = os.getenv("MERCADOLIVRE_ACCESS_TOKEN", "").strip()
    if not token:
        return {"items": [], "diagnostic": _diag("Catálogo Mercado Livre", "mercadolivre_catalog", False, "access_token", "not_configured", error="Configure MERCADOLIVRE_ACCESS_TOKEN para consultar o catálogo.")}
    url = "https://api.mercadolibre.com/products/search"
    params = {"status": "active", "site_id": site, "q": query, "limit": 8}
    started = time.perf_counter()
    response = None
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url, headers={"Authorization": f"Bearer {token}"}, params=params)
        latency = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            return {"items": [], "diagnostic": _diag("Catálogo Mercado Livre", "mercadolivre_catalog", True, "access_token", _status_for_http(response.status_code), error=_safe_error(response, f"HTTP {response.status_code}"), latency_ms=latency, http_status=response.status_code)}
        payload = response.json()
        rows = []
        for item in payload.get("results", [])[:8]:
            attrs = {a.get("id"): a.get("value_name") for a in item.get("attributes") or [] if a.get("id") and a.get("value_name")}
            rows.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "domain_id": item.get("domain_id"),
                "attributes": attrs,
            })
        return {"items": rows, "diagnostic": _diag("Catálogo Mercado Livre", "mercadolivre_catalog", True, "access_token", "ok", returned=len(rows), latency_ms=latency, http_status=response.status_code)}
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return {"items": [], "diagnostic": _diag("Catálogo Mercado Livre", "mercadolivre_catalog", True, "access_token", "network_error", error=str(exc)[:260], latency_ms=latency)}


async def _ebay_token() -> Dict:
    client_id = os.getenv("EBAY_CLIENT_ID", "").strip()
    client_secret = os.getenv("EBAY_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        _EBAY_TOKEN_CACHE.update({"token": None, "expires_at": 0.0, "client_id": None})
        return {"token": None, "error": "Configure EBAY_CLIENT_ID e EBAY_CLIENT_SECRET."}

    now = time.time()
    cached = _EBAY_TOKEN_CACHE.get("token")
    cached_client = _EBAY_TOKEN_CACHE.get("client_id")
    if cached and cached_client == client_id and float(_EBAY_TOKEN_CACHE.get("expires_at") or 0) > now + 60:
        return {"token": cached, "error": ""}
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"}
    data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"}
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            r = await client.post("https://api.ebay.com/identity/v1/oauth2/token", headers=headers, data=data)
        if r.status_code >= 400:
            return {"token": None, "error": _safe_error(r, f"OAuth HTTP {r.status_code}")}
        body = r.json()
        token = body.get("access_token")
        if token:
            _EBAY_TOKEN_CACHE["token"] = token
            _EBAY_TOKEN_CACHE["expires_at"] = now + int(body.get("expires_in") or 7200)
            _EBAY_TOKEN_CACHE["client_id"] = client_id
        return {"token": token, "error": "" if token else "OAuth não retornou access_token."}
    except Exception as exc:
        return {"token": None, "error": str(exc)[:260]}


async def search_ebay_live(query: str, marketplace: str = "EBAY_US", source_name: str = "eBay", gtin: str = "") -> Dict:
    configured = bool(os.getenv("EBAY_CLIENT_ID", "").strip() and os.getenv("EBAY_CLIENT_SECRET", "").strip())
    if not configured:
        return {"items": [], "diagnostic": _diag(source_name, "ebay", False, "oauth_client_credentials", "not_configured", error="Configure EBAY_CLIENT_ID e EBAY_CLIENT_SECRET.")}
    started = time.perf_counter()
    token_result = await _ebay_token()
    token = token_result.get("token")
    if not token:
        latency = int((time.perf_counter() - started) * 1000)
        return {"items": [], "diagnostic": _diag(source_name, "ebay", True, "oauth_client_credentials", "auth_required", error=token_result.get("error") or "Não foi possível obter token do eBay.", latency_ms=latency)}

    headers = {"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": marketplace}
    params = {"limit": "50", "filter": "conditions:{NEW}"}
    if gtin.strip():
        params["gtin"] = gtin.strip()
    else:
        params["q"] = query
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"
    response = None
    try:
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as client:
            response = await client.get(url, headers=headers, params=params)
        latency = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            return {"items": [], "diagnostic": _diag(source_name, "ebay", True, "oauth_client_credentials", _status_for_http(response.status_code), error=_safe_error(response, f"HTTP {response.status_code}"), latency_ms=latency, http_status=response.status_code)}
        payload = response.json()
        out: List[Dict] = []
        for item in payload.get("itemSummaries", []):
            price = item.get("price") or {}
            if not price.get("value"):
                continue
            seller = item.get("seller") or {}
            shipping_options = item.get("shippingOptions") or []
            shipping_cost = None
            if shipping_options:
                shipping_cost = (shipping_options[0].get("shippingCost") or {}).get("value")
            out.append(_clean_listing(
                source_name,
                item.get("title", query),
                float(price.get("value")),
                price.get("currency", "USD"),
                item.get("itemWebUrl", ""),
                item.get("condition", "New"),
                {
                    "item_id": item.get("itemId"),
                    "epid": item.get("epid"),
                    "categories": item.get("categories") or [],
                    "seller_username": seller.get("username"),
                    "seller_feedback_percent": seller.get("feedbackPercentage"),
                    "seller_feedback_score": seller.get("feedbackScore"),
                    "shipping_cost": shipping_cost,
                },
            ))
        return {"items": out, "diagnostic": _diag(source_name, "ebay", True, "oauth_client_credentials", "ok", returned=len(out), latency_ms=latency, http_status=response.status_code, total=payload.get("total"))}
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return {"items": [], "diagnostic": _diag(source_name, "ebay", True, "oauth_client_credentials", "network_error", error=str(exc)[:260], latency_ms=latency)}


async def search_google_shopping_live(query: str, country: str = "BR", source_name: str = "Google Shopping") -> Dict:
    api_key = os.getenv("SERPAPI_KEY", "").strip()
    if not api_key:
        return {"items": [], "diagnostic": _diag(source_name, "google_shopping", False, "api_key", "not_configured", error="Configure SERPAPI_KEY para ativar o Google Shopping.")}
    gl, hl, fallback_currency = SERP_COUNTRY.get(country, (country.lower(), "en", "USD"))
    params = {
        "engine": "google_shopping",
        "q": query,
        "gl": gl,
        "hl": hl,
        "api_key": api_key,
        "output": "json",
    }
    started = time.perf_counter()
    response = None
    try:
        async with httpx.AsyncClient(timeout=max(DEFAULT_TIMEOUT, 20), follow_redirects=True) as client:
            response = await client.get("https://serpapi.com/search", params=params)
        latency = int((time.perf_counter() - started) * 1000)
        if response.status_code >= 400:
            return {"items": [], "diagnostic": _diag(source_name, "google_shopping", True, "api_key", _status_for_http(response.status_code), error=_safe_error(response, f"HTTP {response.status_code}"), latency_ms=latency, http_status=response.status_code)}
        payload = response.json()
        if payload.get("error"):
            return {"items": [], "diagnostic": _diag(source_name, "google_shopping", True, "api_key", "upstream_error", error=str(payload.get("error"))[:260], latency_ms=latency, http_status=response.status_code)}
        out: List[Dict] = []
        for item in payload.get("shopping_results", []) or []:
            extracted = item.get("extracted_price")
            if extracted in (None, 0):
                continue
            merchant = item.get("source") or "Loja não informada"
            currency = (item.get("price") or "").strip()
            # SerpApi's extracted_price is numeric but the currency code is not always separate.
            # For localized shopping searches, the country currency is the safest structured fallback.
            out.append(_clean_listing(
                source_name,
                item.get("title", query),
                float(extracted),
                fallback_currency,
                item.get("product_link") or item.get("link") or "",
                "used" if item.get("second_hand_condition") else "new",
                {
                    "merchant": merchant,
                    "product_id": item.get("product_id"),
                    "rating": item.get("rating"),
                    "reviews": item.get("reviews"),
                    "delivery": item.get("delivery"),
                    "price_text": currency,
                    "position": item.get("position"),
                },
            ))
        return {"items": out, "diagnostic": _diag(source_name, "google_shopping", True, "api_key", "ok", returned=len(out), latency_ms=latency, http_status=response.status_code, search_id=(payload.get("search_metadata") or {}).get("id"))}
    except Exception as exc:
        latency = int((time.perf_counter() - started) * 1000)
        return {"items": [], "diagnostic": _diag(source_name, "google_shopping", True, "api_key", "network_error", error=str(exc)[:260], latency_ms=latency)}


def integration_configuration() -> List[Dict]:
    ml = bool(os.getenv("MERCADOLIVRE_ACCESS_TOKEN", "").strip())
    ebay = bool(os.getenv("EBAY_CLIENT_ID", "").strip() and os.getenv("EBAY_CLIENT_SECRET", "").strip())
    serp = bool(os.getenv("SERPAPI_KEY", "").strip())
    vision = bool(os.getenv("OPENAI_API_KEY", "").strip())
    return [
        {"id": "mercadolivre", "name": "Mercado Livre", "configured": ml, "mode": "Access token" if ml else "Tentativa pública", "countries": ["BR", "MX", "AR"], "required_env": ["MERCADOLIVRE_ACCESS_TOKEN"]},
        {"id": "ebay", "name": "eBay", "configured": ebay, "mode": "OAuth client credentials" if ebay else "Não configurado", "countries": ["US", "FR", "DE", "GB"], "required_env": ["EBAY_CLIENT_ID", "EBAY_CLIENT_SECRET"]},
        {"id": "google_shopping", "name": "Google Shopping via SerpApi", "configured": serp, "mode": "API key" if serp else "Não configurado", "countries": list(SERP_COUNTRY.keys()), "required_env": ["SERPAPI_KEY"]},
        {"id": "bcb", "name": "Banco Central — PTAX", "configured": True, "mode": "API pública", "countries": ["BR"], "required_env": []},
        {"id": "vision", "name": "Visão por IA", "configured": vision, "mode": "OpenAI Responses API" if vision else "Fallback pelo nome", "countries": [], "required_env": ["OPENAI_API_KEY"]},
    ]
