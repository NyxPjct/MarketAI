import asyncio
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.main import app
from app.db import Base, SessionLocal
from app.models import CatalogProduct, CatalogRevision, CatalogAnalysis, ProductWatch, AnalysisHistory
from app.history import record_analysis
from app.batch_csv import AnalysisFields
from app.catalog import fingerprint
from app import batch_worker
from test_batches import result


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def account(client):
    data = client.post('/v1/auth/register', json={'email': f'{uuid4().hex}@example.com', 'password': 'CatalogTest123!', 'accept_terms': True}).json()
    headers = {'Authorization': 'Bearer ' + data['access_token'], 'x-device-id': 'catalog-device'}
    assert client.post('/v1/devices/activate', headers=headers, json={'device_uuid': 'catalog-device'}).status_code == 200
    return headers, data['user']['id']


def add(client, headers, sku='001-PHONE', **fields):
    response = client.post('/v1/catalog/import', headers=headers, json={'products': [
        {'fields': {'sku': sku, 'product_name': 'Phone', 'purchase_cost': 50, **fields}, 'stock': 5}]})
    assert response.status_code == 200, response.text
    return response.json()['items'][0]


def selection(product):
    return {'products': [{'id': product['id'], 'revision': product['revision']}]}


def save_result(user_id, fields, reliable=True):
    from app.models import User
    with SessionLocal() as db:
        return record_analysis(db, db.get(User, user_id), result(fields, reliable))


def test_import_unique_sku_validation_idempotence_and_atomic_conflicts(client):
    headers, _ = account(client)
    first = add(client, headers)
    assert first['fields']['sku'] == '001-PHONE' and first['revision'] == 1
    assert add(client, headers)['id'] == first['id']
    for sku in ('001-phone', '００１-PHONE'):
        response = client.post('/v1/catalog/import', headers=headers, json={'products': [{'fields': {'sku': sku, 'product_name': 'Other'}}]})
        assert response.status_code == 409
    response = client.post('/v1/catalog/import', headers=headers, json={'products': [
        {'fields': {'sku': 'new', 'product_name': 'New'}}, {'fields': {'sku': '001-PHONE', 'product_name': 'Conflict'}}]})
    assert response.status_code == 409
    assert client.get('/v1/catalog', headers=headers).json()['total'] == 1
    for fields in ({'sku': ' ', 'product_name': 'x'}, {'sku': 'x', 'product_name': 'x', 'purchase_cost': -1},
                   {'sku': 'x', 'product_name': 'x', 'ads_percent': 80}):
        assert client.post('/v1/catalog/import', headers=headers, json={'products': [{'fields': fields}]}).status_code == 422
    assert client.post('/v1/catalog/import', headers=headers, json={'products': [
        {'fields': {'sku': 'X', 'product_name': 'x'}}, {'fields': {'sku': 'x', 'product_name': 'x'}}]}).status_code == 422


def test_catalog_and_every_action_are_private(client):
    headers, _ = account(client)
    other, _ = account(client)
    product = add(client, headers)
    assert client.get('/v1/catalog', headers=other).json()['total'] == 0
    assert client.get('/v1/catalog').status_code == 401
    assert client.get(f"/v1/catalog/{product['id']}/revisions", headers=other).status_code == 404
    assert client.put(f"/v1/catalog/{product['id']}", headers=other,
                      json={'fields': product['fields'], 'revision': 1}).status_code == 404
    assert client.delete(f"/v1/catalog/{product['id']}?revision=1", headers=other).status_code == 404
    for action in ('monitor', 'analyze'):
        payload = {**selection(product), 'client_id': str(uuid4())} if action == 'analyze' else selection(product)
        assert client.post('/v1/catalog/'+action, headers=other, json=payload).status_code == 404


def test_revisions_protect_against_overwrites_and_sku_changes(client):
    headers, _ = account(client)
    product = add(client, headers)
    updated = {**product['fields'], 'purchase_cost': 75, 'supplier_name': 'New supplier'}
    payload = {'fields': updated, 'stock': 8, 'revision': 1}
    response = client.put('/v1/catalog/'+product['id'], headers=headers, json=payload)
    assert response.status_code == 200 and response.json()['revision'] == 2
    assert client.put('/v1/catalog/'+product['id'], headers=headers, json=payload).status_code == 409
    assert client.delete('/v1/catalog/'+product['id']+'?revision=1', headers=headers).status_code == 409
    assert client.put('/v1/catalog/'+product['id'], headers=headers, json={**payload, 'revision': 2, 'fields': {**updated, 'sku': 'other'}}).status_code == 422
    history = client.get('/v1/catalog/'+product['id']+'/revisions', headers=headers).json()
    assert [item['revision'] for item in history['items']] == [2, 1]
    assert [item['fields']['purchase_cost'] for item in history['items']] == [75, 50]
    assert [item['stock'] for item in history['items']] == [8, 5]


def test_comparison_uses_trusted_results_and_marks_changed_inputs(client):
    headers, user_id = account(client)
    product = add(client, headers)
    analysis_id = save_result(user_id, product['fields'])
    current = client.get('/v1/catalog', headers=headers).json()['items'][0]
    assert current['latest']['analysis_id'] == analysis_id
    assert current['latest']['net_margin_percent'] == 35 and not current['latest']['outdated']
    # Stock and supplier changes preserve the calculation; changed costs do not.
    updated = {**product['fields'], 'supplier_name': 'Another supplier'}
    for revision, cost in ((1, 50), (2, 70)):
        updated['purchase_cost'] = cost
        assert client.put('/v1/catalog/'+product['id'], headers=headers,
                          json={'fields': updated, 'stock': 9, 'revision': revision}).status_code == 200
        row = client.get('/v1/catalog', headers=headers).json()['items'][0]
        assert row['latest']['outdated'] is (cost != 50)
    assert client.get('/v1/catalog?freshness=outdated', headers=headers).json()['total'] == 1
    assert client.get('/v1/catalog?freshness=current', headers=headers).json()['total'] == 0
    save_result(user_id, updated, reliable=False)
    latest = client.get('/v1/catalog', headers=headers).json()['items'][0]['latest']
    assert latest['recommended_price'] is None and latest['net_margin_percent'] is None
    assert latest['cost_floor'] == 75 and not latest['outdated']
    assert client.get('/v1/catalog?quality=unavailable', headers=headers).json()['total'] == 1


def test_imported_history_never_becomes_catalog_evidence_and_clear_preserves_products(client):
    headers, user_id = account(client)
    product = add(client, headers)
    client.post('/v1/history/import', headers=headers, json={'items': [{'client_id': str(uuid4()),
        'date': '2026-01-01T00:00:00Z', 'name': 'Phone', 'recommended': 999, 'mode': 'reliable'}]})
    assert client.get('/v1/catalog', headers=headers).json()['items'][0]['latest'] is None
    save_result(user_id, product['fields'])
    assert client.delete('/v1/history', headers=headers).status_code == 200
    assert client.get('/v1/catalog', headers=headers).json()['items'][0]['latest'] is None
    with SessionLocal() as db:
        assert db.query(CatalogAnalysis).join(CatalogProduct).filter(CatalogProduct.user_id == user_id).count() == 0


def test_catalog_analysis_reuses_durable_batch_and_captured_inputs(client, monkeypatch):
    headers, user_id = account(client)
    product = add(client, headers)
    payload = {**selection(product), 'client_id': str(uuid4())}
    assert client.post('/v1/catalog/analyze', headers={**headers, 'x-device-id': 'wrong'}, json=payload).status_code == 403
    response = client.post('/v1/catalog/analyze', headers=headers, json=payload)
    assert response.status_code == 200, response.text
    job = response.json()
    assert job['rows'][0]['fields']['sku'] == '001-PHONE'
    assert client.put('/v1/catalog/'+product['id'], headers=headers,
                      json={'fields': {**product['fields'], 'purchase_cost': 80}, 'stock': 5, 'revision': 1}).status_code == 200
    assert client.post('/v1/catalog/analyze', headers=headers, json=payload).json()['id'] == job['id']
    assert client.post('/v1/catalog/analyze', headers=headers, json={**payload, 'client_id': str(uuid4())}).status_code == 409
    async def analysis(fields):
        assert fields['purchase_cost'] == 50
        return result(fields)
    monkeypatch.setattr(batch_worker, 'run_analysis', analysis)
    assert asyncio.run(batch_worker.process_one())
    latest = client.get('/v1/catalog', headers=headers).json()['items'][0]['latest']
    assert latest['outdated'] and latest['net_margin_percent'] == 35


def test_bulk_monitor_is_idempotent_and_updates_costs_without_reactivation(client):
    headers, _ = account(client)
    first = add(client, headers, sku='A')
    second = add(client, headers, sku='B')
    payload = {'products': selection(first)['products'] + selection(second)['products']}
    response = client.post('/v1/catalog/monitor', headers=headers, json=payload)
    assert response.status_code == 200, response.text
    watches = [item['watch_id'] for item in response.json()['items']]
    assert len(set(watches)) == 2  # Same product name, distinct SKU/cost context.
    assert [item['watch_id'] for item in client.post('/v1/catalog/monitor', headers=headers, json=payload).json()['items']] == watches
    # A manual watch for the same name must not overwrite catalog configuration.
    client.post('/v1/intelligence/watches', headers=headers, json={'product_name': 'Phone', 'purchase_cost': 3})
    assert len(client.get('/v1/intelligence/watches', headers=headers).json()['items']) == 3
    client.delete('/v1/intelligence/watches/'+watches[0], headers=headers)
    assert client.put('/v1/catalog/'+first['id'], headers=headers, json={
        'fields': {**first['fields'], 'purchase_cost': 90}, 'stock': 8, 'revision': 1}).status_code == 200
    with SessionLocal() as db:
        watch = db.get(ProductWatch, watches[0])
        assert not watch.active and json.loads(watch.settings_json)['purchase_cost'] == 90
    assert client.post('/v1/catalog/monitor', headers=headers, json=selection(first)).status_code == 409
    fresh = client.get('/v1/catalog?q=A', headers=headers).json()['items'][0]
    assert client.post('/v1/catalog/monitor', headers=headers, json=selection(fresh)).json()['items'][0]['monitoring']


def test_delete_pauses_monitor_and_keeps_saved_analysis(client):
    headers, user_id = account(client)
    product = add(client, headers)
    analysis_id = save_result(user_id, product['fields'])
    watch_id = client.post('/v1/catalog/monitor', headers=headers, json=selection(product)).json()['items'][0]['watch_id']
    assert client.delete('/v1/catalog/'+product['id']+'?revision=1', headers=headers).status_code == 200
    assert client.get('/v1/catalog', headers=headers).json()['total'] == 0
    assert client.get('/v1/history/'+analysis_id, headers=headers).status_code == 200
    with SessionLocal() as db:
        assert not db.get(ProductWatch, watch_id).active
        assert db.query(CatalogRevision).filter_by(product_id=product['id']).count() == 0
        assert db.query(CatalogAnalysis).filter_by(product_id=product['id']).count() == 0


def test_search_filters_pagination_and_nulls_sort_last(client):
    headers, user_id = account(client)
    first = add(client, headers, sku='A%_')
    second = add(client, headers, sku='B')
    save_result(user_id, first['fields'])
    rows = client.get('/v1/catalog?sort=margin&limit=1', headers=headers).json()
    assert rows['total'] == 2 and rows['items'][0]['id'] == first['id']
    assert client.get('/v1/catalog?sort=margin&limit=1&offset=1', headers=headers).json()['items'][0]['id'] == second['id']
    assert client.get('/v1/catalog?q=%25_', headers=headers).json()['total'] == 1
    assert client.get('/v1/catalog?freshness=none', headers=headers).json()['items'][0]['id'] == second['id']
    assert client.get('/v1/catalog?quality=reliable', headers=headers).json()['total'] == 1


def test_fingerprint_is_stable_for_defaults_and_numeric_coercion():
    assert fingerprint(AnalysisFields(product_name='X')) == fingerprint(AnalysisFields.model_validate(
        AnalysisFields(product_name='X').model_dump()))


def test_zero_fees_are_preserved_by_the_actual_analysis_engine(monkeypatch):
    from app import market_engine
    async def identify(*args):
        return {'product_name': 'Phone'}
    async def unavailable(*args, **kwargs):
        return {'items': [], 'diagnostic': {'status': 'not_configured'}}
    async def rate(*args):
        return {'rate': 1, 'live': True}
    monkeypatch.setattr(market_engine, 'identify_product', identify)
    monkeypatch.setattr(market_engine, 'search_google_shopping_live', unavailable)
    monkeypatch.setattr(market_engine, 'get_rate_to_brl', rate)
    fields = AnalysisFields(product_name='Phone', destination_country='CA', purchase_cost=50,
                            marketplace_fee_percent=0, taxes_percent=0, ads_percent=0, desired_margin_percent=0).model_dump()
    output = asyncio.run(market_engine.run_analysis(fields))
    assert output['pricing']['costs']['minimum_for_target_margin'] == 50


def test_existing_database_receives_only_additive_tables(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'upgrade.db'))
    old_tables = [table for name, table in Base.metadata.tables.items() if not name.startswith('catalog_')]
    Base.metadata.create_all(engine, tables=old_tables)
    Base.metadata.create_all(engine)
    from sqlalchemy import inspect
    names = inspect(engine).get_table_names()
    assert {'catalog_products', 'catalog_revisions', 'catalog_analyses', 'analysis_history', 'analysis_batches'} <= set(names)
    Base.metadata.create_all(engine)  # Repeatable startup on the upgraded database.
    engine.dispose()
