import asyncio
from uuid import uuid4

from app.db import Base, engine, SessionLocal
from app.models import IntelligenceAlert, MarketSnapshot, ProductWatch, User
from app import sentinel_worker


def test_sentinel_stores_snapshots_and_alerts_without_a_desktop_client(monkeypatch):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        user = User(email=f'{uuid4().hex}@example.com', password_hash='unused-test-hash', status='active')
        db.add(user);db.flush()
        watch = ProductWatch(user_id=user.id, product_name='Monitored phone', settings_json='{"minimum_margin_percent":15}')
        db.add(watch);db.commit();db.refresh(watch)
        prices = iter([100,120])
        async def analysis(fields):
            price = next(prices)
            return {'market':{'reliable':True,'pricing_count':5,'live_source_count':1,'quality':{'state':'reliable','average_match_score':90}},
                    'pricing':{'market':{'median':price,'min':price-5,'max':price+5,'count':5},
                               'costs':{'unit_cost':50,'minimum_for_target_margin':70,'desired_margin_percent':20},
                               'strategies':{'recommended':{'price':price,'net_margin_percent':12}}}}
        monkeypatch.setattr(sentinel_worker,'run_analysis',analysis)
        asyncio.run(sentinel_worker.check_one(db,watch,user))
        asyncio.run(sentinel_worker.check_one(db,watch,user))
        snapshots=db.query(MarketSnapshot).filter_by(user_id=user.id,watch_id=watch.id).all()
        alerts=db.query(IntelligenceAlert).filter_by(user_id=user.id,watch_id=watch.id).all()
        assert [x.market_median for x in snapshots] == [100,120]
        assert any(x.kind=='price_move' and '20.0%' in x.title for x in alerts)
        assert any(x.kind=='margin' and x.severity=='critical' for x in alerts)
        assert all(x.user_id==user.id and x.watch_id==watch.id for x in alerts)
