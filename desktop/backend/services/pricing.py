from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable, List, Dict, Optional


def percentile(values: List[float], p: float) -> float:
    if not values:
        return 0.0
    data = sorted(values)
    if len(data) == 1:
        return data[0]
    k = (len(data) - 1) * p
    f = int(k)
    c = min(f + 1, len(data) - 1)
    if f == c:
        return data[f]
    return data[f] + (data[c] - data[f]) * (k - f)


def money(v: float) -> float:
    return round(float(v) + 1e-9, 2)


@dataclass
class PricingInputs:
    purchase_cost_brl: float
    freight_brl: float = 0.0
    import_cost_brl: float = 0.0
    packaging_brl: float = 0.0
    other_costs_brl: float = 0.0
    marketplace_fee_percent: float = 0.0
    taxes_percent: float = 0.0
    ads_percent: float = 0.0
    desired_margin_percent: float = 20.0

    @property
    def unit_cost(self) -> float:
        return max(0.0, self.purchase_cost_brl + self.freight_brl + self.import_cost_brl + self.packaging_brl + self.other_costs_brl)

    @property
    def variable_rate(self) -> float:
        return max(0.0, (self.marketplace_fee_percent + self.taxes_percent + self.ads_percent) / 100.0)

    @property
    def target_margin(self) -> float:
        return max(0.0, self.desired_margin_percent / 100.0)


def sale_metrics(price: float, inputs: PricingInputs) -> Dict[str, float]:
    rate = inputs.variable_rate
    variable_cost = price * rate
    profit = price - variable_cost - inputs.unit_cost
    margin = (profit / price * 100.0) if price > 0 else 0.0
    roi = (profit / inputs.unit_cost * 100.0) if inputs.unit_cost > 0 else 0.0
    return {
        "price": money(price),
        "variable_costs": money(variable_cost),
        "unit_cost": money(inputs.unit_cost),
        "net_profit": money(profit),
        "net_margin_percent": round(margin, 2),
        "roi_percent": round(roi, 2),
    }


def build_pricing(prices: Iterable[float], inputs: PricingInputs) -> Dict:
    """Build pricing only from supplied, already-validated market prices.

    The reliable-market engine deliberately does NOT manufacture a market recommendation when ``prices`` is
    empty. In that case the API returns a cost floor / target-margin floor only. This
    prevents a cost-derived number from masquerading as a real market price.
    """
    valid = sorted([float(x) for x in prices if x and x > 0])

    market_min = min(valid) if valid else 0.0
    market_max = max(valid) if valid else 0.0
    market_median = median(valid) if valid else 0.0
    p25 = percentile(valid, 0.25) if valid else 0.0
    p75 = percentile(valid, 0.75) if valid else 0.0
    market_avg = sum(valid) / len(valid) if valid else 0.0

    denominator_break_even = 1.0 - inputs.variable_rate
    denominator_target = 1.0 - inputs.variable_rate - inputs.target_margin

    break_even = inputs.unit_cost / denominator_break_even if denominator_break_even > 0.01 else inputs.unit_cost * 10
    minimum_target = inputs.unit_cost / denominator_target if denominator_target > 0.01 else break_even * 1.5
    cost_floor = sale_metrics(minimum_target, inputs)

    strategies: Dict[str, Optional[Dict]]
    opportunity: Dict[str, object]
    simulation: Dict[str, object]

    if valid:
        fast = max(minimum_target, p25 * 0.985)
        competitive = max(minimum_target, market_median * 0.995)
        margin = max(minimum_target * 1.025, market_median * 1.025)
        premium = max(margin * 1.045, p75)

        recommended = competitive
        rec_metrics = sale_metrics(recommended, inputs)

        headroom = (market_median - minimum_target) / minimum_target if minimum_target > 0 else 0
        headroom_score = max(0.0, min(45.0, 25.0 + headroom * 70.0))
        sample_score = min(20.0, len(valid) * 1.5)
        margin_score = max(0.0, min(25.0, rec_metrics["net_margin_percent"] * 1.1))
        spread = ((p75 - p25) / market_median) if market_median else 1.0
        stability_score = max(0.0, min(10.0, 10.0 - spread * 20.0))
        score = max(0, min(100, int(round(headroom_score + sample_score + margin_score + stability_score))))
        if score >= 80:
            label, signal = "Excelente oportunidade", "green"
        elif score >= 65:
            label, signal = "Boa oportunidade", "green"
        elif score >= 45:
            label, signal = "Oportunidade moderada", "yellow"
        else:
            label, signal = "Margem apertada", "red"

        delta_to_market = ((market_median - recommended) / market_median * 100.0) if market_median else 0.0
        strategies = {
            "fast_sale": sale_metrics(fast, inputs),
            "recommended": rec_metrics,
            "margin": sale_metrics(margin, inputs),
            "premium": sale_metrics(premium, inputs),
        }
        opportunity = {"score": score, "label": label, "signal": signal, "market_based": True}
        simulation = {
            "available": True,
            "min_price": money(max(break_even, market_min * 0.80 if market_min else break_even)),
            "max_price": money(max(premium * 1.20, market_max * 1.10 if market_max else premium * 1.20)),
            "initial_price": money(recommended),
        }
        position = {"recommended_vs_median_percent": round(delta_to_market, 2)}
    else:
        strategies = {
            "fast_sale": None,
            "recommended": None,
            "margin": None,
            "premium": None,
        }
        opportunity = {
            "score": None,
            "label": "Sem mercado confiável",
            "signal": "neutral",
            "market_based": False,
        }
        simulation = {
            "available": False,
            "min_price": money(break_even),
            "max_price": money(max(minimum_target * 1.5, break_even + 1)),
            "initial_price": money(minimum_target),
        }
        position = {"recommended_vs_median_percent": None}

    return {
        "market": {
            "count": len(valid),
            "min": money(market_min),
            "p25": money(p25),
            "average": money(market_avg),
            "median": money(market_median),
            "p75": money(p75),
            "max": money(market_max),
        },
        "costs": {
            "unit_cost": money(inputs.unit_cost),
            "break_even": money(break_even),
            "minimum_for_target_margin": money(minimum_target),
            "variable_rate_percent": round(inputs.variable_rate * 100, 2),
            "desired_margin_percent": round(inputs.desired_margin_percent, 2),
            "purchase_cost_brl": money(inputs.purchase_cost_brl),
            "freight_brl": money(inputs.freight_brl),
            "import_cost_brl": money(inputs.import_cost_brl),
            "packaging_brl": money(inputs.packaging_brl),
            "other_costs_brl": money(inputs.other_costs_brl),
        },
        "cost_floor": cost_floor,
        "strategies": strategies,
        "opportunity": opportunity,
        "position": position,
        "simulation": simulation,
    }
