from __future__ import annotations
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import User
from app.security import decode_access_token
from app.config import settings

def current_user(authorization:str|None=Header(None),db:Session=Depends(get_db)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401,"authentication_required")
    try: payload=decode_access_token(authorization.split(" ",1)[1])
    except Exception: raise HTTPException(401,"invalid_or_expired_token")
    user=db.get(User,payload.get("sub"))
    if not user or user.status!="active" or user.deleted_at is not None: raise HTTPException(401,"account_unavailable")
    return user

def admin_auth(x_admin_key:str|None=Header(None)):
    if not settings.admin_api_key or not x_admin_key or x_admin_key!=settings.admin_api_key: raise HTTPException(403,"admin_key_required")
    return True


def current_admin(authorization:str|None=Header(None),db:Session=Depends(get_db)):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401,"admin_authentication_required")
    try: payload=decode_access_token(authorization.split(" ",1)[1])
    except Exception: raise HTTPException(401,"invalid_or_expired_admin_token")
    user=db.get(User,payload.get("sub"))
    if not user or user.role!="admin" or user.status!="active" or user.deleted_at is not None:
        raise HTTPException(403,"admin_access_required")
    return user
