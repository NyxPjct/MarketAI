from app.intelligence_engine import profit_engine, forecast_series, data_quality_score

def test_profit_engine_real_margin():
    r=profit_engine({"sale_price":200,"unit_cost":100,"marketplace_fee_percent":16,"taxes_percent":6,"ads_percent":3,"payment_fee_percent":2,"minimum_margin_percent":10})
    assert r["net_profit"] == 46.0
    assert r["net_margin_percent"] == 23.0
    assert r["healthy"] is True

def test_forecast_requires_real_snapshots():
    assert forecast_series([100])["available"] is False
    r=forecast_series([100,110,120,130])
    assert r["available"] is True
    assert r["direction"] == "alta"

def test_quality_blocks_no_market():
    r=data_quality_score({"market":{"quality":{"state":"unavailable","average_match_score":0},"pricing_count":0,"live_source_count":0}})
    assert r["score"] == 0
