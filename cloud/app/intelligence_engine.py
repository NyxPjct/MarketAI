from __future__ import annotations
import math
from statistics import mean, median


def clamp(value, low=0.0, high=100.0):
    return max(low, min(high, float(value)))


def data_quality_score(analysis: dict) -> dict:
    market = analysis.get("market") or {}
    q = market.get("quality") or {}
    state = q.get("state") or "unavailable"
    base = {"reliable": 62, "insufficient": 35, "ambiguous": 24, "no_match": 12, "unavailable": 0}.get(state, 0)
    match = clamp(q.get("average_match_score") or 0)
    used = int(market.get("pricing_count") or 0)
    sources = int(market.get("live_source_count") or 0)
    score = clamp(base + min(18, used * 2.2) + min(10, sources * 5) + match * 0.10)
    return {
        "score": round(score, 1),
        "grade": "A" if score >= 85 else "B" if score >= 70 else "C" if score >= 50 else "D" if score >= 30 else "E",
        "state": state,
        "explanation": "Combina confiabilidade da amostra, compatibilidade dos anúncios, quantidade usada e diversidade de fontes.",
    }


def market_score(analysis: dict) -> dict:
    quality = data_quality_score(analysis)
    pricing = analysis.get("pricing") or {}
    market = pricing.get("market") or {}
    costs = pricing.get("costs") or {}
    strategy = (pricing.get("strategies") or {}).get("recommended") or {}
    med = float(market.get("median") or 0)
    minimum = float(costs.get("minimum_for_target_margin") or 0)
    margin = float(strategy.get("net_margin_percent") or 0)
    count = int(market.get("count") or 0)
    if quality["state"] != "reliable" or med <= 0:
        return {"score": None, "label": "Bloqueado", "quality": quality, "components": {}, "reason": "Sem amostra confiável, o Market Score não é liberado."}
    margin_component = clamp((margin / max(1.0, float(costs.get("desired_margin_percent") or 20))) * 30, 0, 35)
    headroom = ((med - minimum) / med * 100) if med else 0
    headroom_component = clamp(headroom * 1.0, 0, 25)
    confidence_component = quality["score"] * 0.25
    liquidity_component = clamp(count * 1.5, 0, 15)
    score = clamp(margin_component + headroom_component + confidence_component + liquidity_component)
    label = "EXCEPCIONAL" if score >= 88 else "MUITO FORTE" if score >= 78 else "FORTE" if score >= 66 else "MODERADO" if score >= 50 else "FRACO"
    return {
        "score": round(score, 1), "label": label, "quality": quality,
        "components": {"margin": round(margin_component,1), "headroom": round(headroom_component,1), "confidence": round(confidence_component,1), "liquidity": round(liquidity_component,1)},
        "reason": "Score proprietário MarketAI baseado em margem, folga de preço, qualidade dos dados e profundidade da amostra.",
    }


def profit_engine(payload: dict) -> dict:
    price = float(payload.get("sale_price") or 0)
    unit_cost = float(payload.get("unit_cost") or 0)
    fee = float(payload.get("marketplace_fee_percent") or 0)
    taxes = float(payload.get("taxes_percent") or 0)
    ads = float(payload.get("ads_percent") or 0)
    payment = float(payload.get("payment_fee_percent") or 0)
    returns = float(payload.get("return_loss_percent") or 0)
    fixed = float(payload.get("fixed_cost_per_unit") or 0)
    total_pct = fee + taxes + ads + payment + returns
    variable = price * total_pct / 100
    net_profit = price - unit_cost - fixed - variable
    margin = (net_profit / price * 100) if price else 0
    roi = (net_profit / (unit_cost + fixed) * 100) if (unit_cost + fixed) else 0
    denom = 1 - total_pct / 100
    break_even = ((unit_cost + fixed) / denom) if denom > 0 else None
    return {
        "sale_price": round(price,2), "unit_cost": round(unit_cost,2), "variable_fees": round(variable,2),
        "fixed_cost": round(fixed,2), "net_profit": round(net_profit,2), "net_margin_percent": round(margin,2),
        "roi_percent": round(roi,2), "break_even_price": round(break_even,2) if break_even is not None else None,
        "total_variable_percent": round(total_pct,2),
        "healthy": net_profit > 0 and margin >= float(payload.get("minimum_margin_percent") or 15),
    }


def autopilot_price(analysis: dict, strategy="balanced", undercut=1.0, min_margin=15.0) -> dict:
    pricing = analysis.get("pricing") or {}
    market = pricing.get("market") or {}
    costs = pricing.get("costs") or {}
    if not analysis.get("market",{}).get("reliable"):
        return {"available": False, "reason": "Sem mercado confiável."}
    med = float(market.get("median") or 0)
    low = float(market.get("min") or med)
    high = float(market.get("max") or med)
    floor = float(costs.get("minimum_for_target_margin") or 0)
    if strategy == "aggressive": target = max(floor, low - float(undercut))
    elif strategy == "premium": target = max(floor, med + (high-med)*0.35)
    else: target = max(floor, med - float(undercut))
    rates = float(costs.get("marketplace_fee_percent") or 0)+float(costs.get("taxes_percent") or 0)+float(costs.get("ads_percent") or 0)
    unit = float(costs.get("unit_cost") or 0)
    denom = 1-rates/100-float(min_margin)/100
    margin_floor = unit/denom if denom>0 else floor
    target=max(target, margin_floor)
    return {"available": True, "strategy": strategy, "suggested_price": round(target,2), "market_median": round(med,2), "hard_floor": round(max(floor,margin_floor),2), "min_margin_percent": float(min_margin)}


def forecast_series(values: list[float], horizons=(7,30,60)) -> dict:
    vals=[float(v) for v in values if v is not None and float(v)>0]
    if len(vals)<2:
        return {"available":False,"reason":"São necessários pelo menos 2 snapshots reais."}
    n=len(vals); xs=list(range(n)); xbar=mean(xs); ybar=mean(vals)
    den=sum((x-xbar)**2 for x in xs) or 1
    slope=sum((x-xbar)*(y-ybar) for x,y in zip(xs,vals))/den
    residuals=[y-(ybar+slope*(x-xbar)) for x,y in zip(xs,vals)]
    volatility=(math.sqrt(mean([r*r for r in residuals]))/ybar*100) if ybar else 0
    forecasts={str(h):round(max(0,ybar+slope*((n-1+h)-xbar)),2) for h in horizons}
    direction="alta" if slope>0.15 else "queda" if slope<-0.15 else "estável"
    return {"available":True,"points":n,"last":round(vals[-1],2),"trend_per_snapshot":round(slope,3),"direction":direction,"volatility_percent":round(volatility,2),"forecast":forecasts,"method":"regressão linear simples sobre snapshots reais"}
