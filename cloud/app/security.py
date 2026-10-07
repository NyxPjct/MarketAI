from __future__ import annotations
import hashlib, secrets
from datetime import datetime, timedelta, timezone
import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from app.config import settings

ph=PasswordHasher()
def hash_password(password:str)->str: return ph.hash(password)
def verify_password(password:str, hashed:str)->bool:
    try: return ph.verify(hashed,password)
    except VerifyMismatchError: return False

def token_hash(token:str)->str: return hashlib.sha256(token.encode()).hexdigest()
def new_refresh_token()->str: return secrets.token_urlsafe(48)
def create_access_token(user_id:str, role:str="user"):
    now=datetime.now(timezone.utc)
    return jwt.encode({"sub":user_id,"role":role,"iat":int(now.timestamp()),"exp":int((now+timedelta(minutes=settings.access_minutes)).timestamp()),"iss":"marketai-cloud"},settings.jwt_secret,algorithm="HS256")
def decode_access_token(token:str):
    return jwt.decode(token,settings.jwt_secret,algorithms=["HS256"],issuer="marketai-cloud")
def license_hash(code:str)->str: return hashlib.sha256(code.strip().upper().encode()).hexdigest()
def generate_license_code()->str:
    raw=secrets.token_hex(10).upper()
    return "MAI-"+"-".join(raw[i:i+5] for i in range(0,20,5))
