from __future__ import annotations
import asyncio, json, os
from datetime import datetime, timezone
from app.db import SessionLocal, Base, engine
from app.models import ProductWatch, User, MarketSnapshot, IntelligenceAlert
from app.market_engine import run_analysis
from app.intelligence_engine import data_quality_score, market_score, autopilot_price

INTERVAL=max(15,int(os.getenv("SENTINEL_INTERVAL_MINUTES","60")))
BATCH=max(1,int(os.getenv("SENTINEL_BATCH_SIZE","50")))

def utcnow(): return datetime.now(timezone.utc)

async def check_one(db,w,user):
    try:
        fields=json.loads(w.settings_json or "{}")
        fields.update({"product_name":w.product_name,"variant_text":w.variant_text,"destination_country":w.country})
        analysis=await run_analysis(fields)
        dq=data_quality_score(analysis); ms=market_score(analysis)
        ap=autopilot_price(analysis,str(fields.get("autopilot_strategy") or "balanced"),float(fields.get("undercut_amount") or 1),float(fields.get("minimum_margin_percent") or fields.get("desired_margin_percent") or 15)) if w.autopilot_enabled else {"available":False}
        pm=analysis.get("pricing",{}).get("market",{}); rec=analysis.get("pricing",{}).get("strategies",{}).get("recommended") or {}
        prev=db.query(MarketSnapshot).filter_by(watch_id=w.id,user_id=user.id).order_by(MarketSnapshot.created_at.desc()).first()
        snap=MarketSnapshot(watch_id=w.id,user_id=user.id,market_median=float(pm.get("median") or 0) or None,market_min=float(pm.get("min") or 0) or None,market_max=float(pm.get("max") or 0) or None,listing_count=int(pm.get("count") or 0),quality_score=dq["score"],market_score=ms.get("score"),net_margin=rec.get("net_margin_percent"),suggested_price=(ap.get("suggested_price") if ap.get("available") else rec.get("price")),payload_json=json.dumps({"quality":dq,"score":ms,"autopilot":ap},ensure_ascii=False))
        db.add(snap)
        if prev and snap.market_median and prev.market_median:
            pct=(snap.market_median-prev.market_median)/prev.market_median*100
            if abs(pct)>=8:
                db.add(IntelligenceAlert(user_id=user.id,watch_id=w.id,severity="opportunity" if pct>0 else "attention",kind="price_move",title=f"Preço de mercado {'subiu' if pct>0 else 'caiu'} {abs(pct):.1f}%",message=f"{w.product_name}: R$ {prev.market_median:.2f} → R$ {snap.market_median:.2f}."))
        if rec and float(rec.get("net_margin_percent") or 0)<float(fields.get("minimum_margin_percent") or 15):
            db.add(IntelligenceAlert(user_id=user.id,watch_id=w.id,severity="critical",kind="margin",title="Margem abaixo do limite",message=f"{w.product_name}: margem líquida estimada em {float(rec.get('net_margin_percent') or 0):.1f}%."))
        w.updated_at=utcnow(); db.commit()
    except Exception as exc:
        db.rollback(); db.add(IntelligenceAlert(user_id=user.id,watch_id=w.id,severity="info",kind="source_error",title="Sentinel não conseguiu verificar o produto",message=f"{w.product_name}: {type(exc).__name__}")); db.commit()

async def cycle():
    db=SessionLocal()
    try:
        rows=db.query(ProductWatch).filter_by(active=True).order_by(ProductWatch.updated_at.asc()).limit(BATCH).all()
        for w in rows:
            user=db.get(User,w.user_id)
            if user and user.status=="active": await check_one(db,w,user)
    finally: db.close()

async def main():
    Base.metadata.create_all(engine)
    while True:
        await cycle(); await asyncio.sleep(INTERVAL*60)

if __name__=="__main__": asyncio.run(main())
