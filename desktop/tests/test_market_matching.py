from backend.services.market import filter_compatible_listings
from backend.services.pricing import PricingInputs, build_pricing


def listing(title, price=800):
    return {
        "source": "Teste",
        "title": title,
        "price": price,
        "price_brl": price,
        "currency": "BRL",
        "url": "",
        "condition": "new",
        "metadata": {},
    }


def test_dior_rejects_wrong_variants_and_decants():
    identity = {
        "product_name": "Dior Sauvage",
        "brand": "Dior",
        "model": "Sauvage",
        "category": "Perfume",
        "concentration": "edp",
        "volume_ml": 100,
        "attributes": [],
    }
    rows = [
        listing("Dior Sauvage Eau de Parfum EDP 100ml", 900),
        listing("Dior Sauvage Eau de Toilette EDT 100ml", 700),
        listing("Decant Dior Sauvage EDP 10ml", 90),
        listing("Dior Sauvage EDP 60ml", 650),
    ]
    accepted, rejected, ambiguity = filter_compatible_listings(
        rows, identity, "Dior Sauvage", "100 ml Eau de Parfum", strict=True
    )
    assert len(accepted) == 1
    assert "Eau de Parfum" in accepted[0]["title"]
    assert len(rejected) == 3
    assert ambiguity["ambiguous"] is False


def test_missing_variant_blocks_mixed_concentrations():
    identity = {
        "product_name": "Dior Sauvage",
        "brand": "Dior",
        "model": "Sauvage",
        "category": "Perfume",
        "attributes": [],
    }
    rows = [
        listing("Dior Sauvage EDT 100ml", 700),
        listing("Dior Sauvage EDP 100ml", 900),
        listing("Dior Sauvage Parfum 100ml", 1100),
    ]
    accepted, rejected, ambiguity = filter_compatible_listings(
        rows, identity, "Dior Sauvage", "", strict=True
    )
    assert len(accepted) == 3
    assert ambiguity["ambiguous"] is True
    assert any("concentrações" in x.lower() for x in ambiguity["blockers"])


def test_no_market_does_not_create_recommendation():
    inp = PricingInputs(
        purchase_cost_brl=100,
        marketplace_fee_percent=15,
        taxes_percent=5,
        ads_percent=2,
        desired_margin_percent=20,
    )
    out = build_pricing([], inp)
    assert out["market"]["count"] == 0
    assert out["strategies"]["recommended"] is None
    assert out["opportunity"]["score"] is None
    assert out["cost_floor"]["price"] > 0
