"""Compact summaries produced only from server-side analysis results."""


def summary_for(result):
    pricing = result.get('pricing') or {}
    market = result.get('market') or {}
    rec = ((pricing.get('strategies') or {}).get('recommended') or {}) if market.get('reliable') else {}
    return {'quality': (market.get('quality') or {}).get('state', 'unavailable'),
            'recommended_price': rec.get('price'), 'net_profit': rec.get('net_profit'),
            'net_margin_percent': rec.get('net_margin_percent'),
            'cost_floor': (pricing.get('costs') or {}).get('minimum_for_target_margin'),
            'collected_at': market.get('checked_at'),
            'currency_fallback': (result.get('fx') or {}).get('live') is False}
