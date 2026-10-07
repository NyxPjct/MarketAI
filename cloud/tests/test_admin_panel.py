from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import User
from app.security import hash_password

client = TestClient(app)


def ensure_admin():
    db=SessionLocal()
    try:
        u=db.query(User).filter_by(email='owner@marketai.test').first()
        if not u:
            u=User(email='owner@marketai.test',password_hash=hash_password('AdminStrong123!'),full_name='Owner',role='admin',status='active',email_verified=True)
            db.add(u); db.commit(); db.refresh(u)
        return u.id
    finally: db.close()


def admin_headers():
    ensure_admin()
    r=client.post('/v1/admin/auth/login',json={'email':'owner@marketai.test','password':'AdminStrong123!'})
    assert r.status_code==200,r.text
    return {'Authorization':'Bearer '+r.json()['access_token']}


def ensure_customer(email='admin-customer@example.com'):
    r=client.post('/v1/auth/register',json={'email':email,'password':'SenhaForte123!','full_name':'Cliente Admin','accept_terms':True,'device_uuid':'pc-admin-test'})
    if r.status_code==409:
        db=SessionLocal(); u=db.query(User).filter_by(email=email).first(); uid=u.id; db.close(); return uid
    assert r.status_code==200,r.text
    return r.json()['user']['id']


def test_admin_panel_static_and_dashboard():
    assert client.get('/admin').status_code==200
    h=admin_headers()
    r=client.get('/v1/admin/dashboard',headers=h)
    assert r.status_code==200,r.text
    assert 'metrics' in r.json() and 'users' in r.json()['metrics']


def test_admin_can_block_and_release_customer():
    uid=ensure_customer('admin-block@example.com')
    h=admin_headers()
    r=client.patch(f'/v1/admin/users/{uid}/status',headers=h,json={'status':'blocked'})
    assert r.status_code==200 and r.json()['status']=='blocked'
    r=client.patch(f'/v1/admin/users/{uid}/status',headers=h,json={'status':'active'})
    assert r.status_code==200 and r.json()['status']=='active'


def test_admin_can_grant_plan_and_create_license():
    uid=ensure_customer('admin-plan@example.com')
    h=admin_headers()
    r=client.patch(f'/v1/admin/users/{uid}/subscription',headers=h,json={'plan_code':'pro','status':'active','days':90})
    assert r.status_code==200,r.text
    assert r.json()['subscription']['plan_code']=='pro'
    x=client.post('/v1/admin/licenses/create',headers=h,json={'plan_code':'business','duration_days':365,'max_redemptions':2})
    assert x.status_code==200,x.text
    assert x.json()['license_key'].startswith('MAI-')
    rows=client.get('/v1/admin/licenses',headers=h)
    assert rows.status_code==200 and any(i['id']==x.json()['id'] for i in rows.json()['items'])


def test_non_admin_cannot_access_admin_api():
    r=client.post('/v1/auth/register',json={'email':'not-admin@example.com','password':'SenhaForte123!','full_name':'Normal','accept_terms':True,'device_uuid':'normal-pc'})
    if r.status_code==409:
        r=client.post('/v1/auth/login',json={'email':'not-admin@example.com','password':'SenhaForte123!','device_uuid':'normal-pc'})
    token=r.json()['access_token']
    d=client.get('/v1/admin/dashboard',headers={'Authorization':'Bearer '+token})
    assert d.status_code==403
