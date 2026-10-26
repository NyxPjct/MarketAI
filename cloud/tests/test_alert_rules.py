import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import AlertDetails, IntelligenceAlert, MarketSnapshot, ProductWatch, User, WatchAlertRules
from app import alert_rules, sentinel_worker, watch_collection
from test_catalog import account

AT = datetime(2026,10,26,12,tzinfo=timezone.utc)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def watch(client, headers):
    response = client.post('/v1/intelligence/watches', headers=headers, json={'product_name':'Alert phone'})
    assert response.status_code == 200
    return response.json()['id']


def configure(client, headers, watch_id, **changes):
    url = '/v1/intelligence/watches/'+watch_id+'/alert-rules'
    previous = client.get(url, headers=headers).json()
    response = client.put(url, headers=headers, json={'revision': previous['revision'], 'rules': {**previous['rules'], **changes}})
    assert response.status_code == 200, response.text
    return response.json()


def result(price=100, margin=10, reliable=True):
    return {'market': {'reliable':reliable,'pricing_count':5 if reliable else 0,'live_source_count':1,
                       'quality':{'state':'reliable' if reliable else 'unavailable','average_match_score':90}},
            'pricing': {'market':{'median':price,'min':price,'max':price,'count':5},
                        'costs':{'unit_cost':50,'minimum_for_target_margin':70,'desired_margin_percent':20},
                        'strategies':{'recommended':{'price':price,'net_margin_percent':margin}}}}


def collect(watch_id, output, monkeypatch, at=AT):
    monkeypatch.setattr(watch_collection,'now',lambda:at)
    with SessionLocal() as db:
        stored = db.get(ProductWatch,watch_id)
        watch_collection.persist_snapshot(db,stored,output,json.loads(stored.settings_json))
        db.commit()


def alerts(watch_id, kind=None):
    with SessionLocal() as db:
        query=db.query(IntelligenceAlert).filter_by(watch_id=watch_id)
        return query.filter_by(kind=kind).all() if kind else query.all()


def test_rules_are_private_validated_and_protected_against_concurrent_edits(client):
    headers, _ = account(client);other,_=account(client)
    item=watch(client,headers);url='/v1/intelligence/watches/'+item+'/alert-rules'
    original=client.get(url,headers=headers).json()
    assert original['revision']==0 and original['rules']['price_change_percent']==8
    assert client.get(url,headers=other).status_code==404
    assert client.get(url).status_code==401
    assert client.put(url,headers=other,json={'revision':0,'rules':original['rules']}).status_code==404
    saved=configure(client,headers,item,price_change_percent=20,minimum_margin_percent=0)
    assert saved['revision']==1 and saved['rules']['minimum_margin_percent']==0
    assert client.put(url,headers=headers,json={'revision':0,'rules':original['rules']}).status_code==409
    assert client.put(url,headers=headers,json={'revision':1,'rules':{**original['rules'],'stale_after_hours':0}}).status_code==422
    assert client.put(url,headers=headers,json={'revision':1,'rules':{**original['rules'],'price_enabled':'false'}}).status_code==422


def test_price_threshold_direction_and_cooldown_use_real_collections(client,monkeypatch):
    headers,_=account(client);item=watch(client,headers)
    configure(client,headers,item,price_change_percent=10,price_direction='drop',margin_enabled=False,cooldown_hours=2)
    collect(item,result(100),monkeypatch)
    collect(item,result(115),monkeypatch,AT+timedelta(minutes=1))
    assert not alerts(item,'price_move')
    collect(item,result(95),monkeypatch,AT+timedelta(minutes=2))
    collect(item,result(70),monkeypatch,AT+timedelta(minutes=3))
    assert len(alerts(item,'price_move'))==1
    collect(item,result(50),monkeypatch,AT+timedelta(hours=3))
    assert len(alerts(item,'price_move'))==2
    data=client.get('/v1/intelligence/alerts',headers=headers).json()['items']
    assert all(row['details']['change_percent'] < -10 for row in data)


def test_zero_margin_threshold_is_respected_and_unreliable_data_cannot_trigger_price_or_margin(client,monkeypatch):
    headers,_=account(client);item=watch(client,headers)
    configure(client,headers,item,minimum_margin_percent=0)
    collect(item,result(100,margin=0),monkeypatch)
    assert not alerts(item)
    collect(item,result(500,margin=-20,reliable=False),monkeypatch)
    assert not alerts(item)
    collect(item,result(100,margin=-1),monkeypatch)
    assert len(alerts(item,'margin'))==1


def test_manual_and_worker_checks_share_rules_and_deduplication(client,monkeypatch):
    headers,user_id=account(client);item=watch(client,headers)
    configure(client,headers,item,price_change_percent=5,minimum_margin_percent=20)
    prices=iter([100,120,144])
    async def analysis(*args):return result(next(prices),margin=10)
    monkeypatch.setattr('app.intelligence.run_analysis',analysis)
    monkeypatch.setattr(sentinel_worker,'run_analysis',analysis)
    for _ in range(2):
        assert client.post('/v1/intelligence/watches/'+item+'/check',headers=headers).status_code==200
    with SessionLocal() as db:
        asyncio.run(sentinel_worker.check_one(db,db.get(ProductWatch,item),db.get(User,user_id)))
        assert db.query(MarketSnapshot).filter_by(watch_id=item).count()==3
    assert len(alerts(item,'margin'))==1 and len(alerts(item,'price_move'))==1


def test_staleness_uses_last_valid_collection_even_after_failures_and_empty_snapshots(client,monkeypatch):
    headers,_=account(client);item=watch(client,headers)
    configure(client,headers,item,stale_enabled=True,stale_after_hours=2,cooldown_hours=1,margin_enabled=False)
    collect(item,result(100),monkeypatch,AT)
    collect(item,result(500,reliable=False),monkeypatch,AT+timedelta(hours=3))
    assert len(alerts(item,'stale_data'))==1
    with SessionLocal() as db:
        stored=db.get(ProductWatch,item)
        assert not alert_rules.check_staleness(db,stored,at=AT+timedelta(hours=3,minutes=5))
        assert alert_rules.check_staleness(db,stored,at=AT+timedelta(hours=4))
        db.commit()
    assert len(alerts(item,'stale_data'))==2
    details=client.get('/v1/intelligence/alerts',headers=headers).json()['items'][0]['details']
    assert details['last_valid_at']==AT.isoformat()
    collect(item,result(110),monkeypatch,AT+timedelta(hours=5))
    with SessionLocal() as db:
        assert not alert_rules.check_staleness(db,db.get(ProductWatch,item),at=AT+timedelta(hours=6))


def test_stale_never_collected_and_paused_watches(client,monkeypatch):
    headers,user_id=account(client);item=watch(client,headers)
    configure(client,headers,item,stale_enabled=True,stale_after_hours=1)
    with SessionLocal() as db:
        stored=db.get(ProductWatch,item);stored.created_at=AT
        assert alert_rules.check_staleness(db,stored,at=AT+timedelta(hours=2))
        stored.active=False;db.commit()
        assert not alert_rules.check_staleness(db,stored,at=AT+timedelta(days=2))
    assert len(alerts(item,'stale_data'))==1


def test_all_rules_can_be_disabled_and_failures_are_throttled(client,monkeypatch):
    headers,_=account(client);item=watch(client,headers)
    configure(client,headers,item,price_enabled=False,margin_enabled=False,stale_enabled=False)
    collect(item,result(100,margin=-10),monkeypatch)
    with SessionLocal() as db:
        watch_collection.record_failure(db,db.get(ProductWatch,item));db.commit()
    assert not alerts(item)
    configure(client,headers,item,price_enabled=True)
    with SessionLocal() as db:
        for _ in range(2):watch_collection.record_failure(db,db.get(ProductWatch,item));db.commit()
    assert len(alerts(item,'source_error'))==1


def test_staleness_is_checked_for_watches_outside_worker_collection_batch(client,monkeypatch):
    headers,user_id=account(client);item=watch(client,headers)
    configure(client,headers,item,stale_enabled=True,stale_after_hours=1)
    with SessionLocal() as db:
        stored=db.get(ProductWatch,item);stored.created_at=AT-timedelta(days=2);stored.updated_at=AT
        db.commit()
    async def no_collection(*args):pass
    monkeypatch.setattr(sentinel_worker,'BATCH',1)
    monkeypatch.setattr(sentinel_worker,'check_one',no_collection)
    monkeypatch.setattr(alert_rules,'now',lambda:AT)
    asyncio.run(sentinel_worker.cycle())
    assert len(alerts(item,'stale_data'))==1
