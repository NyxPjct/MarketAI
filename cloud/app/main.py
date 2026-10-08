from __future__ import annotations
import os, secrets, hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Body, File, Form, UploadFile, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.config import settings
from app.db import Base, engine, get_db
from app.models import User, Plan, Subscription, RefreshSession, Device, License, LicenseRedemption, AuditEvent, BillingTransaction, ProviderPlan
from app.security import hash_password, verify_password, create_access_token, new_refresh_token, token_hash, license_hash, generate_license_code
from app.deps import current_user, admin_auth
from app.entitlements import entitlement, consume_analysis
from app.billing import (create_checkout, payment_methods, plan_price, currency_for_country, sync_user_subscription, cancel_subscription, fetch_mp_preapproval, sync_mp_subscription, fetch_mp_payment, sync_pix_payment, verify_mp_signature, verify_stripe_webhook, fetch_stripe_subscription, sync_stripe_subscription, verify_paypal_webhook, fetch_paypal_subscription, sync_paypal_subscription)
from app.market_engine import run_analysis

def utcnow(): return datetime.now(timezone.utc)
def _aware(dt): return dt if (dt is None or dt.tzinfo) else dt.replace(tzinfo=timezone.utc)

def seed(db:Session):
    community=db.get(Plan,"community")
    if not community:
        community=Plan(code="community",name="Community — Gratuito",price_brl=0.0,analyses_per_month=0,device_limit=999999,active=True)
        db.add(community)
    else:
        community.name="Community — Gratuito"; community.price_brl=0.0; community.analyses_per_month=0; community.device_limit=999999; community.active=True
    legacy_defaults=[
        ("essencial","Essencial (legado)",49.90,100,1),
        ("pro","Pro (legado)",99.90,500,2),
        ("business","Business (legado)",199.90,2000,5),
    ]
    for code,name,price,quota,devices in legacy_defaults:
        legacy=db.get(Plan,code)
        if not legacy:
            legacy=Plan(code=code,name=name,price_brl=price,analyses_per_month=quota,device_limit=devices,active=False)
            db.add(legacy)
        else:
            legacy.active=False
    # Existing accounts are migrated to the free Community edition.
    for sub in db.query(Subscription).all():
        sub.plan_code="community"; sub.status="active"; sub.provider="open_source"; sub.trial_end=None; sub.current_period_end=None
    if settings.admin_email and settings.admin_password:
        admin=db.query(User).filter_by(email=settings.admin_email).first()
        if not admin:
            admin=User(email=settings.admin_email,password_hash=hash_password(settings.admin_password),full_name=settings.admin_name,role="admin",status="active",email_verified=True,terms_version=settings.terms_version)
            db.add(admin)
        else:
            admin.role="admin"
            admin.status="active"
            admin.full_name=settings.admin_name or admin.full_name
            admin.password_hash=hash_password(settings.admin_password)
    db.commit()

@asynccontextmanager
async def lifespan(_app):
    Base.metadata.create_all(engine)
    from app.db import SessionLocal
    db=SessionLocal()
    try: seed(db)
    finally: db.close()
    yield

app=FastAPI(title="MarketAI Cloud",version="1.0.3",lifespan=lifespan)

from app.admin import router as admin_router
from app.intelligence import router as intelligence_router
app.include_router(admin_router)
app.include_router(intelligence_router)
ADMIN_DIR=Path(__file__).resolve().parent.parent/"admin"
if settings.admin_panel_enabled and ADMIN_DIR.exists():
    app.mount("/admin/assets", StaticFiles(directory=str(ADMIN_DIR)), name="admin-assets")

@app.get("/admin", include_in_schema=False)
def admin_panel():
    if not settings.admin_panel_enabled or not (ADMIN_DIR/"index.html").exists():
        raise HTTPException(404,"admin_panel_disabled")
    return FileResponse(str(ADMIN_DIR/"index.html"))

@app.get("/health")
def health(): return {"ok":True,"service":"MarketAI Cloud","version":"1.0.3","edition":"Community Open Source","intelligence_core":True,"free":True,"open_source":True}

@app.get("/v1/plans")
def plans(country_code:str="BR",currency:str="",db:Session=Depends(get_db)):
    return {
        "plans":[{
            "code":"community",
            "name":"Community — Gratuito",
            "price_brl":0.0,
            "price":0.0,
            "currency":(currency or currency_for_country(country_code)).upper(),
            "analyses_per_month":None,
            "device_limit":None,
            "unlimited":True,
            "all_features":True,
        }],
        "trial":None,
        "billing_enabled":False,
        "open_source":True,
        "country_code":country_code.upper(),
        "currency":(currency or currency_for_country(country_code)).upper(),
    }

@app.get("/v1/billing/methods")
def billing_methods(country_code:str="BR"):
    return {"country_code":country_code.upper(),"currency":currency_for_country(country_code),"methods":[],"billing_enabled":False,"message":"MarketAI is free and open source."}

def account_payload(db,user):
    return {"user":{"id":user.id,"email":user.email,"full_name":user.full_name,"role":user.role},"entitlement":entitlement(db,user)}

def issue_tokens(db,user,device_uuid=""):
    access=create_access_token(user.id,user.role); refresh=new_refresh_token(); db.add(RefreshSession(user_id=user.id,token_hash=token_hash(refresh),device_uuid=device_uuid,expires_at=utcnow()+timedelta(days=settings.refresh_days))); db.commit()
    return {"access_token":access,"refresh_token":refresh,"token_type":"bearer","expires_in":settings.access_minutes*60,**account_payload(db,user)}

@app.post("/v1/auth/register")
def register(payload:dict=Body(...),db:Session=Depends(get_db)):
    email=str(payload.get("email") or "").strip().lower(); password=str(payload.get("password") or ""); name=str(payload.get("full_name") or "").strip(); accepted=bool(payload.get("accept_terms"))
    if not accepted: raise HTTPException(400,"terms_required")
    if "@" not in email or len(password)<8: raise HTTPException(400,"invalid_email_or_password")
    if db.query(User).filter_by(email=email).first(): raise HTTPException(409,"email_already_registered")
    user=User(email=email,password_hash=hash_password(password),full_name=name,terms_version=settings.terms_version); db.add(user); db.flush()
    sub=Subscription(user_id=user.id,plan_code="community",status="active",provider="open_source",trial_end=None,current_period_end=None); db.add(sub); db.add(AuditEvent(user_id=user.id,event="register",detail="community_account_created")); db.commit(); db.refresh(user)
    return issue_tokens(db,user,str(payload.get("device_uuid") or ""))

@app.post("/v1/auth/login")
def login(payload:dict=Body(...),db:Session=Depends(get_db)):
    email=str(payload.get("email") or "").strip().lower(); password=str(payload.get("password") or "")
    user=db.query(User).filter_by(email=email).first()
    if not user or not verify_password(password,user.password_hash): raise HTTPException(401,"invalid_credentials")
    if user.status!="active": raise HTTPException(403,"account_inactive")
    return issue_tokens(db,user,str(payload.get("device_uuid") or ""))

@app.post("/v1/auth/refresh")
def refresh(payload:dict=Body(...),db:Session=Depends(get_db)):
    token=str(payload.get("refresh_token") or ""); row=db.query(RefreshSession).filter_by(token_hash=token_hash(token),revoked=False).first()
    if not row or _aware(row.expires_at)<=utcnow(): raise HTTPException(401,"invalid_refresh_token")
    user=db.get(User,row.user_id); row.revoked=True; db.commit(); return issue_tokens(db,user,row.device_uuid)

@app.post("/v1/auth/logout")
def logout(payload:dict=Body(...),db:Session=Depends(get_db)):
    token=str(payload.get("refresh_token") or ""); row=db.query(RefreshSession).filter_by(token_hash=token_hash(token)).first()
    if row: row.revoked=True; db.commit()
    return {"ok":True}

@app.get("/v1/account/me")
def me(user:User=Depends(current_user),db:Session=Depends(get_db)): return account_payload(db,user)

@app.post("/v1/devices/activate")
def activate_device(payload:dict=Body(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    device_uuid=str(payload.get("device_uuid") or "").strip(); name=str(payload.get("name") or "Windows PC")[:160]
    if not device_uuid: raise HTTPException(400,"device_uuid_required")
    ent=entitlement(db,user)
    row=db.query(Device).filter_by(user_id=user.id,device_uuid=device_uuid).first()
    if row: row.active=True; row.name=name; row.last_seen=utcnow(); db.commit(); return {"ok":True,"device_id":row.id,"entitlement":ent}
    row=Device(user_id=user.id,device_uuid=device_uuid,name=name); db.add(row); db.commit(); return {"ok":True,"device_id":row.id,"entitlement":entitlement(db,user)}

@app.get("/v1/devices")
def list_devices(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return {"devices":[{"id":d.id,"name":d.name,"device_uuid":d.device_uuid,"active":d.active,"last_seen":d.last_seen.isoformat()} for d in db.query(Device).filter_by(user_id=user.id).all()]}

@app.delete("/v1/devices/{device_id}")
def remove_device(device_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    d=db.query(Device).filter_by(id=device_id,user_id=user.id).first()
    if not d: raise HTTPException(404,"device_not_found")
    d.active=False; db.commit(); return {"ok":True}

@app.post("/v1/licenses/activate")
def activate_license(payload:dict=Body(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    raise HTTPException(410,"licenses_disabled_open_source_edition")

@app.post("/v1/billing/checkout")
async def billing_checkout(payload:dict=Body(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    raise HTTPException(410,"billing_disabled_open_source_edition")

@app.post("/v1/billing/sync")
async def billing_sync(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return account_payload(db,user)

@app.post("/v1/billing/cancel")
async def billing_cancel(user:User=Depends(current_user),db:Session=Depends(get_db)):
    return account_payload(db,user)

@app.post("/v1/webhooks/mercadopago")
async def mercado_pago_webhook(request:Request,db:Session=Depends(get_db)):
    body={}
    try: body=await request.json()
    except Exception: pass
    data=body.get("data") or {}
    obj_id=str(data.get("id") or request.query_params.get("data.id") or request.query_params.get("id") or "")
    typ=str(body.get("type") or request.query_params.get("topic") or "")
    if not verify_mp_signature(request.headers.get("x-signature",""),request.headers.get("x-request-id",""),obj_id):
        raise HTTPException(401,"invalid_webhook_signature")
    if obj_id and typ=="payment":
        try: sync_pix_payment(db,await fetch_mp_payment(obj_id))
        except Exception: pass
    elif obj_id and ("subscription" in typ or typ in {"preapproval","subscription_preapproval"}):
        try: sync_mp_subscription(db,await fetch_mp_preapproval(obj_id))
        except Exception: pass
    return {"ok":True}

@app.post("/v1/webhooks/stripe")
async def stripe_webhook(request:Request,db:Session=Depends(get_db)):
    raw=await request.body()
    if not verify_stripe_webhook(raw,request.headers.get("stripe-signature","")):
        raise HTTPException(401,"invalid_webhook_signature")
    try: body=__import__("json").loads(raw.decode("utf-8"))
    except Exception: body={}
    typ=str(body.get("type") or ""); obj=((body.get("data") or {}).get("object") or {})
    subscription_id=""
    if typ=="checkout.session.completed": subscription_id=str(obj.get("subscription") or "")
    elif typ.startswith("customer.subscription."): subscription_id=str(obj.get("id") or "")
    if subscription_id:
        try: sync_stripe_subscription(db,await fetch_stripe_subscription(subscription_id))
        except Exception: pass
    return {"ok":True}

@app.post("/v1/webhooks/paypal")
async def paypal_webhook(request:Request,db:Session=Depends(get_db)):
    try: body=await request.json()
    except Exception: body={}
    if not await verify_paypal_webhook(request.headers,body):
        raise HTTPException(401,"invalid_webhook_signature")
    resource=body.get("resource") or {}; sid=str(resource.get("id") or resource.get("billing_agreement_id") or "")
    event=str(body.get("event_type") or "")
    if sid and ("BILLING.SUBSCRIPTION" in event or event.startswith("PAYMENT.SALE")):
        try: sync_paypal_subscription(db,await fetch_paypal_subscription(sid))
        except Exception: pass
    return {"ok":True}

@app.post("/v1/analysis")
async def analysis(request:Request,user:User=Depends(current_user),db:Session=Depends(get_db)):
    device_uuid=str(request.headers.get("x-device-id") or "").strip()
    device=db.query(Device).filter_by(user_id=user.id,device_uuid=device_uuid,active=True).first() if device_uuid else None
    if not device:
        raise HTTPException(403,"device_not_authorized")
    device.last_seen=utcnow(); db.commit()
    ent=entitlement(db,user)
    form=await request.form(); fields={k:str(v) for k,v in form.items() if k!="image"}; image=form.get("image"); image_bytes=None; ctype=None
    if image is not None and hasattr(image,"read"):
        image_bytes=await image.read(); ctype=getattr(image,"content_type",None)
    try: result=await run_analysis(fields,image_bytes,ctype)
    except ValueError as e: raise HTTPException(400,str(e))
    ent_after=consume_analysis(db,user); result["account"]={"plan":ent_after["plan_name"],"analyses_remaining":None,"analyses_quota":None,"unlimited":True}; return result

@app.get("/v1/updates/latest")
def latest_update(platform:str="windows",channel:str="stable"):
    path=Path(os.getenv("UPDATE_MANIFEST_PATH",str(Path(__file__).resolve().parent.parent/"releases/windows-stable.json")))
    if not path.exists(): return {"available":False,"version":"1.0.3"}
    import json; return json.loads(path.read_text(encoding="utf-8"))

@app.post("/v1/admin/licenses")
def admin_create_license(payload:dict=Body(...),_:bool=Depends(admin_auth),db:Session=Depends(get_db)):
    plan_code=str(payload.get("plan_code") or "pro"); plan=db.get(Plan,plan_code)
    if not plan: raise HTTPException(404,"plan_not_found")
    code=generate_license_code(); lic=License(code_hash=license_hash(code),code_hint=code[-5:],plan_code=plan_code,duration_days=max(1,int(payload.get("duration_days") or 30)),max_redemptions=max(1,int(payload.get("max_redemptions") or 1))); db.add(lic); db.commit()
    return {"license_key":code,"plan_code":plan_code,"duration_days":lic.duration_days,"max_redemptions":lic.max_redemptions}

@app.get("/v1/admin/stats")
def admin_stats(_:bool=Depends(admin_auth),db:Session=Depends(get_db)):
    return {"users":db.query(User).count(),"active_subscriptions":db.query(Subscription).filter(Subscription.status.in_(["active","trialing"])).count(),"devices":db.query(Device).filter_by(active=True).count()}
