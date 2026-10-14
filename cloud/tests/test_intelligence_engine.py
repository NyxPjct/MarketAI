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


def test_forecast_uses_days_with_irregular_collections():
    r = forecast_series([100, 110, 200], timestamps=['2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z', '2026-01-11T00:00:00Z'])
    assert r['horizon_unit'] == 'day'
    assert r['trend_per_day'] == 10
    assert r['forecast'] == {'7': 270, '30': 500, '60': 800}
    assert r['forecast_dates']['7'].startswith('2026-01-18')
    assert r['history_days'] == 10
    assert r['preliminary']


def test_forecast_sorts_dates_and_preserves_price_date_alignment():
    r = forecast_series([200, None, 100, float('nan'), 110], timestamps=[
        '2026-01-11', '2026-01-03', '2026-01-01', '2026-01-05', '2026-01-02'])
    assert r['points'] == 3
    assert r['forecast']['7'] == 270
    assert r['last'] == 200


def test_forecast_rejects_insufficient_or_invalid_time_points():
    assert not forecast_series([100, 120], timestamps=['2026-01-01', '2026-01-01'])['available']
    assert not forecast_series([100, 120], timestamps=['invalid', '2026-01-01'])['available']
    assert not forecast_series([100, 120], timestamps=['2026-01-01'])['available']


def test_forecast_groups_same_instant_across_timezones():
    r = forecast_series([90, 110, 120], timestamps=['2026-01-01T00:00:00Z', '2025-12-31T21:00:00-03:00', '2026-01-03T00:00:00Z'])
    assert r['points'] == 2
    assert r['trend_per_day'] == 10
    assert r['forecast']['7'] == 190


def test_longer_history_remains_an_extrapolation():
    r = forecast_series([100, 110, 120, 130, 140], timestamps=[f'2026-01-0{i}' for i in range(1, 6)])
    assert not r['preliminary']
    assert 'not_a_guarantee' in r['limitations']
