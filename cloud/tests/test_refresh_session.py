from uuid import uuid4
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import User


def test_inactive_account_cannot_refresh_and_token_is_revoked():
    with TestClient(app) as client:
        data=client.post('/v1/auth/register',json={'email':f'{uuid4().hex}@example.com','password':'RepairTest123!','accept_terms':True}).json()
        with SessionLocal() as db:
            db.get(User,data['user']['id']).status='suspended';db.commit()
        payload={'refresh_token':data['refresh_token']}
        assert client.post('/v1/auth/refresh',json=payload).status_code==403
        assert client.post('/v1/auth/refresh',json=payload).status_code==401
