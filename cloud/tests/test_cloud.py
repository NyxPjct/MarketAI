import os
os.environ["DATABASE_URL"]="sqlite:///./test-marketai-cloud.db"
os.environ["JWT_SECRET"]="test-secret-abcdefghijklmnopqrstuvwxyz"
os.environ["ADMIN_API_KEY"]="admin-test"
from fastapi.testclient import TestClient
from app.main import app, seed
from app.db import Base, engine
Base.metadata.drop_all(engine); Base.metadata.create_all(engine)
from app.db import SessionLocal
_db=SessionLocal(); seed(_db); _db.close()

client=TestClient(app)
def auth(email="test@example.com"):
    r=client.post("/v1/auth/register",json={"email":email,"password":"SenhaForte123!","full_name":"Teste","accept_terms":True,"device_uuid":"pc-1"}); assert r.status_code==200,r.text; return r.json()

def test_register_login_trial_and_device():
    d=auth(); assert d["entitlement"]["active"] is True; assert d["entitlement"]["trialing"] is True
    h={"Authorization":"Bearer "+d["access_token"]}; r=client.post("/v1/devices/activate",headers=h,json={"device_uuid":"pc-1","name":"Meu PC"}); assert r.status_code==200
    me=client.get("/v1/account/me",headers=h); assert me.status_code==200; assert me.json()["entitlement"]["remaining"]==10

def test_manual_license():
    d=auth("license@example.com"); h={"Authorization":"Bearer "+d["access_token"]}
    x=client.post("/v1/admin/licenses",headers={"x-admin-key":"admin-test"},json={"plan_code":"pro","duration_days":90}); assert x.status_code==200
    y=client.post("/v1/licenses/activate",headers=h,json={"license_key":x.json()["license_key"]}); assert y.status_code==200; assert y.json()["entitlement"]["plan_code"]=="pro"; assert y.json()["entitlement"]["status"]=="active"

def test_plans_and_update_manifest():
    assert len(client.get("/v1/plans").json()["plans"])==3
    assert client.get("/v1/updates/latest").status_code==200


def test_analysis_requires_authorized_device(monkeypatch):
    d=auth("devicecheck@example.com"); h={"Authorization":"Bearer "+d["access_token"]}
    r=client.post("/v1/analysis",headers={**h,"x-device-id":"not-activated"},data={"product_name":"Teste"})
    assert r.status_code==403 and r.json()["detail"]=="device_not_authorized"


def test_analysis_consumes_quota_after_success(monkeypatch):
    d=auth("quota@example.com"); h={"Authorization":"Bearer "+d["access_token"],"x-device-id":"pc-1"}
    # authorize this device first
    assert client.post("/v1/devices/activate",headers={"Authorization":"Bearer "+d["access_token"]},json={"device_uuid":"pc-1","name":"PC"}).status_code==200
    async def fake_analysis(fields,image_bytes=None,image_content_type=None):
        return {"product":{"product_name":fields.get("product_name")},"market":{"reliable":False},"pricing":{},"advice":{}}
    import app.main as mainmod
    monkeypatch.setattr(mainmod,"run_analysis",fake_analysis)
    r=client.post("/v1/analysis",headers=h,data={"product_name":"Produto Teste"})
    assert r.status_code==200, r.text
    assert r.json()["account"]["analyses_remaining"]==9
