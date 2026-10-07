from backend.services.pricing import PricingInputs, build_pricing


def test_pricing_engine_hits_target_margin():
    inp = PricingInputs(
        purchase_cost_brl=100,
        marketplace_fee_percent=15,
        taxes_percent=5,
        ads_percent=2,
        desired_margin_percent=20,
    )
    out = build_pricing([190, 200, 210, 220, 230, 240], inp)
    minimum = out["costs"]["minimum_for_target_margin"]
    assert minimum > 0
    assert out["strategies"]["recommended"]["price"] >= minimum
    assert out["strategies"]["recommended"]["net_margin_percent"] >= 19.9
