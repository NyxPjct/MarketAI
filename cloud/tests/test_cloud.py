import os
os.environ["DATABASE_URL"]="sqlite:///./test-marketai-cloud.db"
os.environ["JWT_SECRET"]="test-secret-abcdefghijklmnopqrstuvwxyz"
os.environ["ADMIN_API_KEY"]="admin-test"

from fastapi.testclient import TestClient
from app.main import app, seed
from app.db import Base, engine

Base.metadata.drop_all(engine)
Base.metadata.create_all(engine)

from app.db import SessionLocal

_db=SessionLocal()
seed(_db)
_db.close()

client=TestClient(app)


def auth(email="test@example.com"):
    r=client.post(
        "/v1/auth/register",
        json={
            "email":email,
            "password":"SenhaForte123!",
            "full_name":"Teste",
            "accept_terms":True,
            "device_uuid":"pc-1",
        },
    )
    assert r.status_code==200,r.text
    return r.json()


def test_register_login_community_and_device():
    d=auth()
    ent=d["entitlement"]
    assert ent["active"] is True
    assert ent["trialing"] is False
    assert ent["plan_code"]=="community"
    assert ent["unlimited"] is True
    assert ent["price"]==0

    h={"Authorization":"Bearer "+d["access_token"]}
    r=client.post(
        "/v1/devices/activate",
        headers=h,
        json={"device_uuid":"pc-1","name":"Meu PC"},
    )
    assert r.status_code==200

    me=client.get("/v1/account/me",headers=h)
    assert me.status_code==200
    account=me.json()["entitlement"]
    assert account["remaining"] is None
    assert account["quota"] is None
    assert "copilot" in account["features"]
    assert "radar" in account["features"]


def test_license_activation_is_disabled_in_open_source_edition():
    d=auth("license@example.com")
    h={"Authorization":"Bearer "+d["access_token"]}
    y=client.post(
        "/v1/licenses/activate",
        headers=h,
        json={"license_key":"MAI-NOT-NEEDED"},
    )
    assert y.status_code==410
    assert y.json()["detail"]=="licenses_disabled_open_source_edition"


def test_plans_are_free_and_update_manifest_exists():
    payload=client.get("/v1/plans").json()
    assert payload["billing_enabled"] is False
    assert len(payload["plans"])==1
    assert payload["plans"][0]["code"]=="community"
    assert payload["plans"][0]["price"]==0
    assert payload["plans"][0]["unlimited"] is True
    assert client.get("/v1/updates/latest").status_code==200


def test_billing_checkout_is_disabled():
    d=auth("billing-disabled@example.com")
    h={"Authorization":"Bearer "+d["access_token"]}
    r=client.post(
        "/v1/billing/checkout",
        headers=h,
        json={"plan_code":"pro","payment_method":"card"},
    )
    assert r.status_code==410
    assert r.json()["detail"]=="billing_disabled_open_source_edition"


def test_analysis_requires_authorized_device(monkeypatch):
    d=auth("devicecheck@example.com")
    h={"Authorization":"Bearer "+d["access_token"]}
    r=client.post(
        "/v1/analysis",
        headers={**h,"x-device-id":"not-activated"},
        data={"product_name":"Teste"},
    )
    assert r.status_code==403
    assert r.json()["detail"]=="device_not_authorized"


def test_analysis_is_unlimited_but_usage_is_tracked(monkeypatch):
    d=auth("community-analysis@example.com")
    h={
        "Authorization":"Bearer "+d["access_token"],
        "x-device-id":"pc-1",
    }
    assert client.post(
        "/v1/devices/activate",
        headers={"Authorization":"Bearer "+d["access_token"]},
        json={"device_uuid":"pc-1","name":"PC"},
    ).status_code==200

    async def fake_analysis(fields,image_bytes=None,image_content_type=None):
        return {
            "product":{"product_name":fields.get("product_name")},
            "market":{"reliable":False},
            "pricing":{},
            "advice":{},
        }

    import app.main as mainmod
    monkeypatch.setattr(mainmod,"run_analysis",fake_analysis)

    r=client.post("/v1/analysis",headers=h,data={"product_name":"Produto Teste"})
    assert r.status_code==200,r.text
    assert r.json()["account"]["analyses_remaining"] is None
    assert r.json()["account"]["analyses_quota"] is None
    assert r.json()["account"]["unlimited"] is True

    me=client.get("/v1/account/me",headers={"Authorization":"Bearer "+d["access_token"]})
    assert me.json()["entitlement"]["used"]>=1
