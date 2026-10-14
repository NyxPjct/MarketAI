"""Explain the data and calculations behind a recommendation."""
from collections import Counter


def recommendation_evidence(analysis):
    market = analysis.get("market") or {}
    pricing = analysis.get("pricing") or {}
    quality = market.get("quality") or {}
    rec = (pricing.get("strategies") or {}).get("recommended") or {}
    costs = pricing.get("costs") or {}
    return {
        "collected_at": market.get("checked_at"),
        "state": quality.get("state", "unavailable"),
        "recommendation_available": bool(market.get("reliable") and rec),
        "counts": {"found": market.get("raw_count", 0), "compatible": market.get("matched_count", 0),
                   "used": market.get("pricing_count", 0), "discarded": market.get("discarded_count", 0)},
        "minimum_required": quality.get("minimum_required", 3),
        "blockers": quality.get("blockers") or [],
        "discard_reasons": dict(Counter(x.get("rejection_reason") or "incompatible"
                                        for x in market.get("discarded") or [])),
        "discard_reasons_scope": "displayed_listings",
        "cost_floor": costs.get("minimum_for_target_margin"),
        "net_margin_percent": rec.get("net_margin_percent"),
        "target_margin_percent": costs.get("desired_margin_percent"),
        "method": "compatible_listing_median_and_declared_costs",
        "limitations": ["listing_prices_not_completed_sales", "matching_not_authenticity"],
        "currency_fallback": bool(analysis.get("fx") and not analysis["fx"].get("live")),
    }
