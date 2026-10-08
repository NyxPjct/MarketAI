from __future__ import annotations
import json, os
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.deps import current_user
from app.entitlements import entitlement
from app.market_engine import run_analysis
from app.models import User, ProductWatch, MarketSnapshot, IntelligenceAlert
from app.intelligence_engine import data_quality_score, market_score, profit_engine, autopilot_price, forecast_series

router=APIRouter(prefix="/v1/intelligence",tags=["intelligence"])
def now(): return datetime.now(timezone.utc)

ALL_FEATURES={"profit","sentinel","radar","forecast","copilot","autopilot","api","teams","enterprise"}

def features(_plan=None):
    return sorted(ALL_FEATURES)

def limit_for(_plan=None):
    return None

def require(db,user,feature):
    ent=entitlement(db,user)
    if not ent.get("active"): raise HTTPException(401,"authentication_required")
    return ent

def watch_json(w):
    try: settings=json.loads(w.settings_json or "{}")
    except: settings={}
    return {"id":w.id,"product_name":w.product_name,"variant_text":w.variant_text,"country":w.country,"active":w.active,"autopilot_enabled":w.autopilot_enabled,"settings":settings,"created_at":w.created_at.isoformat(),"updated_at":w.updated_at.isoformat()}

@router.get("/capabilities")
def capabilities(user:User=Depends(current_user),db:Session=Depends(get_db)):
    ent=entitlement(db,user)
    return {"plan":"community","features":features(),"watch_limit":None,"unlimited":True,"open_source":True}

@router.post("/profit")
def profit(payload:dict=Body(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    require(db,user,"profit"); return profit_engine(payload)

@router.post("/market-score")
def score(payload:dict=Body(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    require(db,user,"profit"); return market_score(payload)

@router.get("/watches")
def watches(user:User=Depends(current_user),db:Session=Depends(get_db)):
    require(db,user,"sentinel"); rows=db.query(ProductWatch).filter_by(user_id=user.id).order_by(ProductWatch.created_at.desc()).all(); return {"items":[watch_json(x) for x in rows]}

@router.post("/watches")
def create_watch(payload:dict=Body(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    require(db,user,"sentinel")
    name=str(payload.get("product_name") or "").strip()
    if not name: raise HTTPException(400,"product_name_required")
    variant=str(payload.get("variant_text") or "")
    country=str(payload.get("destination_country") or "BR").upper()
    existing=db.query(ProductWatch).filter_by(user_id=user.id,product_name=name,variant_text=variant,country=country,active=True).first()
    if existing:
        existing.settings_json=json.dumps(payload,ensure_ascii=False); existing.autopilot_enabled=bool(payload.get("autopilot_enabled")); existing.updated_at=now(); db.commit(); db.refresh(existing); return watch_json(existing)
    w=ProductWatch(user_id=user.id,product_name=name,variant_text=variant,country=country,settings_json=json.dumps(payload,ensure_ascii=False),autopilot_enabled=bool(payload.get("autopilot_enabled")))
    db.add(w);db.commit();db.refresh(w);return watch_json(w)

@router.delete("/watches/{watch_id}")
def delete_watch(watch_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    w=db.query(ProductWatch).filter_by(id=watch_id,user_id=user.id).first()
    if not w: raise HTTPException(404,"watch_not_found")
    w.active=False;w.updated_at=now();db.commit();return {"ok":True}

@router.get("/watches/{watch_id}/history")
def history(watch_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    w=db.query(ProductWatch).filter_by(id=watch_id,user_id=user.id).first()
    if not w: raise HTTPException(404,"watch_not_found")
    rows=db.query(MarketSnapshot).filter_by(watch_id=w.id,user_id=user.id).order_by(MarketSnapshot.created_at.asc()).all()
    return {"watch":watch_json(w),"snapshots":[{"id":x.id,"median":x.market_median,"min":x.market_min,"max":x.market_max,"listing_count":x.listing_count,"quality_score":x.quality_score,"market_score":x.market_score,"net_margin":x.net_margin,"suggested_price":x.suggested_price,"created_at":x.created_at.isoformat()} for x in rows]}

@router.post("/watches/{watch_id}/check")
async def check_watch(watch_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    w=db.query(ProductWatch).filter_by(id=watch_id,user_id=user.id,active=True).first()
    if not w: raise HTTPException(404,"watch_not_found")
    fields=json.loads(w.settings_json or "{}"); fields["product_name"]=w.product_name;fields["variant_text"]=w.variant_text;fields["destination_country"]=w.country
    analysis=await run_analysis(fields)
    dq=data_quality_score(analysis); ms=market_score(analysis)
    ap=autopilot_price(analysis,str(fields.get("autopilot_strategy") or "balanced"),float(fields.get("undercut_amount") or 1),float(fields.get("minimum_margin_percent") or fields.get("desired_margin_percent") or 15)) if w.autopilot_enabled else {"available":False,"reason":"Autopilot desativado."}
    pm=analysis.get("pricing",{}).get("market",{}); rec=analysis.get("pricing",{}).get("strategies",{}).get("recommended") or {}
    snap=MarketSnapshot(watch_id=w.id,user_id=user.id,market_median=float(pm.get("median") or 0) or None,market_min=float(pm.get("min") or 0) or None,market_max=float(pm.get("max") or 0) or None,listing_count=int(pm.get("count") or 0),quality_score=dq["score"],market_score=ms.get("score"),net_margin=rec.get("net_margin_percent"),suggested_price=(ap.get("suggested_price") if ap.get("available") else rec.get("price")),payload_json=json.dumps({"quality":dq,"score":ms,"autopilot":ap},ensure_ascii=False))
    prev=db.query(MarketSnapshot).filter_by(watch_id=w.id,user_id=user.id).order_by(MarketSnapshot.created_at.desc()).first();db.add(snap)
    if prev and snap.market_median and prev.market_median:
        pct=(snap.market_median-prev.market_median)/prev.market_median*100
        if abs(pct)>=8:
            direction="subiu" if pct>0 else "caiu"; db.add(IntelligenceAlert(user_id=user.id,watch_id=w.id,severity="opportunity" if pct>0 else "attention",kind="price_move",title=f"Preço de mercado {direction} {abs(pct):.1f}%",message=f"{w.product_name}: mediana foi de R$ {prev.market_median:.2f} para R$ {snap.market_median:.2f}."))
    if rec and float(rec.get("net_margin_percent") or 0)<float(fields.get("minimum_margin_percent") or 15):
        db.add(IntelligenceAlert(user_id=user.id,watch_id=w.id,severity="critical",kind="margin",title="Margem abaixo do limite",message=f"{w.product_name}: margem líquida estimada em {float(rec.get('net_margin_percent') or 0):.1f}%."))
    w.updated_at=now();db.commit();db.refresh(snap)
    return {"watch":watch_json(w),"analysis":analysis,"data_quality":dq,"market_score":ms,"autopilot":ap,"snapshot_id":snap.id}

@router.get("/radar")
def radar(user:User=Depends(current_user),db:Session=Depends(get_db)):
    require(db,user,"radar"); rows=db.query(ProductWatch).filter_by(user_id=user.id,active=True).all(); out=[]
    for w in rows:
        snaps=db.query(MarketSnapshot).filter_by(watch_id=w.id,user_id=user.id).order_by(MarketSnapshot.created_at.desc()).limit(2).all()
        if not snaps: continue
        s=snaps[0]; trend=0
        if len(snaps)>1 and snaps[1].market_median and s.market_median: trend=(s.market_median-snaps[1].market_median)/snaps[1].market_median*100
        base=float(s.market_score or 0); momentum=max(-10,min(10,trend)); rank=max(0,min(100,base+momentum*0.6))
        out.append({"watch_id":w.id,"product_name":w.product_name,"variant_text":w.variant_text,"score":round(rank,1),"market_score":s.market_score,"price_trend_percent":round(trend,2),"median":s.market_median,"quality_score":s.quality_score,"listing_count":s.listing_count})
    return {"items":sorted(out,key=lambda x:x["score"],reverse=True),"method":"somente snapshots reais coletados pelo Sentinel"}

@router.get("/alerts")
def alerts(user:User=Depends(current_user),db:Session=Depends(get_db)):
    require(db,user,"sentinel"); rows=db.query(IntelligenceAlert).filter_by(user_id=user.id).order_by(IntelligenceAlert.created_at.desc()).limit(100).all(); return {"items":[{"id":x.id,"watch_id":x.watch_id,"severity":x.severity,"kind":x.kind,"title":x.title,"message":x.message,"acknowledged":x.acknowledged,"created_at":x.created_at.isoformat()} for x in rows]}

@router.post("/alerts/{alert_id}/ack")
def ack(alert_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    x=db.query(IntelligenceAlert).filter_by(id=alert_id,user_id=user.id).first()
    if not x: raise HTTPException(404,"alert_not_found")
    x.acknowledged=True;db.commit();return {"ok":True}

@router.get("/forecast/{watch_id}")
def forecast(watch_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    require(db,user,"forecast"); rows=db.query(MarketSnapshot).filter_by(watch_id=watch_id,user_id=user.id).order_by(MarketSnapshot.created_at.asc()).all(); return forecast_series([x.market_median for x in rows])

@router.post("/copilot")
async def copilot(payload:dict=Body(...),user:User=Depends(current_user),db:Session=Depends(get_db)):
    require(db,user,"copilot"); question=str(payload.get("question") or "").strip()
    if not question: raise HTTPException(400,"question_required")
    radar_data=radar(user,db); alerts_data=alerts(user,db); context={"radar":radar_data["items"][:10],"alerts":alerts_data["items"][:10],"question":question}
    key=os.getenv("OPENAI_API_KEY","").strip(); model=os.getenv("OPENAI_COPILOT_MODEL","").strip()
    if key and model:
        prompt="Você é o MarketAI Copilot. Responda em português, usando SOMENTE os dados JSON fornecidos. Se faltar dado, diga que falta. Não invente preço, venda ou estoque.\n"+json.dumps(context,ensure_ascii=False)
        try:
            async with httpx.AsyncClient(timeout=35) as c:
                r=await c.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json={"model":model,"input":prompt})
                if r.is_success:
                    d=r.json(); text="".join(x.get("text","") for o in d.get("output",[]) for x in o.get("content",[]) if x.get("type")=="output_text")
                    if text: return {"answer":text,"mode":"ai","context":context}
        except Exception: pass
    top=radar_data["items"][0] if radar_data["items"] else None; critical=[x for x in alerts_data["items"] if not x["acknowledged"] and x["severity"]=="critical"]
    if top: answer=f"Hoje, o produto mais forte no Radar é {top['product_name']} com score {top['score']}/100. A mediana mais recente é {('R$ %.2f' % top['median']) if top['median'] else 'indisponível'}."
    else: answer="Ainda não há snapshots suficientes no Radar. Adicione produtos ao Sentinel e execute verificações reais."
    if critical: answer+=f" Existem {len(critical)} alerta(s) crítico(s) não reconhecido(s); vale revisar margem e preço antes de aumentar estoque."
    return {"answer":answer,"mode":"deterministic","context":context}
