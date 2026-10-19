import asyncio
import csv
import io
import json
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import AnalysisBatch, AnalysisBatchItem, User
from app import batch_worker
from app.batches import finalize_batch, now
from app.history import record_analysis
from app.entitlements import consume_analysis


@pytest.fixture
def client():
    with TestClient(app) as c:
        c.batch_users = []
        yield c
        with SessionLocal() as db:
            for batch in db.query(AnalysisBatch).filter(AnalysisBatch.user_id.in_(c.batch_users), AnalysisBatch.active_owner.is_not(None)):
                db.query(AnalysisBatchItem).filter(AnalysisBatchItem.batch_id == batch.id, AnalysisBatchItem.status.in_(['queued', 'running'])).update({'status': 'cancelled'})
                batch.status = 'cancelling'
                db.flush()
                finalize_batch(db, batch)
            db.commit()


def account(client):
    data = client.post('/v1/auth/register', json={'email': f'{uuid4().hex}@example.com', 'password': 'BatchTest123!', 'accept_terms': True}).json()
    client.batch_users.append(data['user']['id'])
    headers = {'Authorization': 'Bearer ' + data['access_token'], 'x-device-id': 'batch-device'}
    assert client.post('/v1/devices/activate', headers=headers, json={'device_uuid': 'batch-device'}).status_code == 200
    return headers, data['user']['id']


def create(client, headers, names=('Phone', 'Perfume')):
    payload = {'client_id': str(uuid4()), 'rows': [{'line': i+2, 'fields': {'product_name': name, 'purchase_cost': 50}} for i, name in enumerate(names)]}
    response = client.post('/v1/batches', headers=headers, json=payload)
    assert response.status_code == 200, response.text
    return response.json(), payload


def result(fields, reliable=True):
    return {'product': {'product_name': fields['product_name']}, 'request': fields,
            'market': {'reliable': reliable, 'checked_at': now().isoformat(), 'quality': {'state': 'reliable' if reliable else 'unavailable'}},
            'pricing': {'strategies': {'recommended': {'price': 100, 'net_profit': 35, 'net_margin_percent': 35}} if reliable else {},
                        'costs': {'minimum_for_target_margin': 75}, 'market': {'median': 100} if reliable else {}}}


def test_preview_is_authenticated_and_never_calls_providers(client, monkeypatch):
    headers, _ = account(client)
    async def forbidden(*args):
        pytest.fail('Preview must not query providers')
    monkeypatch.setattr(batch_worker, 'run_analysis', forbidden)
    assert client.post('/v1/batches/preview', files={'file': ('p.csv', b'product_name\nPhone')}).status_code == 401
    response = client.post('/v1/batches/preview', headers=headers, files={'file': ('p.csv', b'product_name;purchase_cost\nPhone;25\nInvalid;-5\n')})
    assert response.status_code == 200
    assert response.json()['valid_count'] == response.json()['invalid_count'] == 1


def test_submission_requires_device_and_revalidates_fields(client):
    headers, _ = account(client)
    job, payload = create(client, headers, ('Phone',))
    assert client.post('/v1/batches', headers={**headers, 'x-device-id': 'unknown'}, json=payload).status_code == 403
    payload['rows'][0]['fields']['purchase_cost'] = -10
    assert client.post('/v1/batches', headers=headers, json=payload).status_code == 422
    payload['rows'][0]['fields']['purchase_cost'] = 50
    payload['rows'] *= 51
    assert client.post('/v1/batches', headers=headers, json=payload).status_code == 422


def test_creation_is_idempotent_and_one_active_batch_per_account(client):
    headers, _ = account(client)
    job, payload = create(client, headers)
    assert client.post('/v1/batches', headers=headers, json=payload).json()['id'] == job['id']
    payload['client_id'] = str(uuid4())
    assert client.post('/v1/batches', headers=headers, json=payload).status_code == 409
    client.post(f"/v1/batches/{job['id']}/cancel", headers=headers)
    assert client.post('/v1/batches', headers=headers, json=payload).status_code == 200


def test_all_batch_operations_are_account_private(client):
    owner, _ = account(client)
    other, _ = account(client)
    job, _ = create(client, owner)
    assert client.get('/v1/batches', headers=other).json()['items'] == []
    for suffix in ['', '/export']:
        assert client.get(f"/v1/batches/{job['id']}{suffix}", headers=other).status_code == 404
    assert client.post(f"/v1/batches/{job['id']}/cancel", headers=other).status_code == 404


def test_batch_saves_history_and_blocks_prices_without_evidence(client, monkeypatch):
    headers, _ = account(client)
    job, _ = create(client, headers)
    async def analysis(fields):
        return result(fields, reliable=fields['product_name'] == 'Phone')
    monkeypatch.setattr(batch_worker, 'run_analysis', analysis)
    for _ in range(2):
        assert asyncio.run(batch_worker.process_one())
    complete = client.get('/v1/batches/' + job['id'], headers=headers).json()
    assert complete['status'] == 'completed' and complete['counts']['completed'] == 2
    by_name = {row['fields']['product_name']: row for row in complete['rows']}
    assert by_name['Phone']['summary']['recommended_price'] == 100
    assert by_name['Perfume']['summary']['recommended_price'] is None
    assert by_name['Perfume']['summary']['quality'] == 'unavailable'
    assert len(client.get('/v1/history', headers=headers).json()['items']) == 2
    assert client.get('/v1/account/me', headers=headers).json()['entitlement']['used'] == 2
    assert not asyncio.run(batch_worker.process_one())


def test_one_failure_does_not_stop_other_products(client, monkeypatch):
    headers, _ = account(client)
    job, _ = create(client, headers)
    async def analysis(fields):
        if fields['product_name'] == 'Phone':
            raise TimeoutError('a provider failure')
        return result(fields)
    monkeypatch.setattr(batch_worker, 'run_analysis', analysis)
    for _ in range(2):
        asyncio.run(batch_worker.process_one())
    complete = client.get('/v1/batches/' + job['id'], headers=headers).json()
    assert complete['status'] == 'completed_with_errors'
    assert complete['counts']['failed'] == complete['counts']['completed'] == 1
    assert complete['rows'][0]['error_code'] == 'analysis_timeout'
    assert 'provider failure' not in json.dumps(complete)
    assert len(client.get('/v1/history', headers=headers).json()['items']) == 1


def test_cancel_finishes_current_product_and_stops_the_rest(client, monkeypatch):
    headers, _ = account(client)
    job, _ = create(client, headers)
    async def scenario():
        started, release = asyncio.Event(), asyncio.Event()
        async def analysis(fields):
            started.set()
            await release.wait()
            return result(fields)
        monkeypatch.setattr(batch_worker, 'run_analysis', analysis)
        task = asyncio.create_task(batch_worker.process_one())
        await started.wait()
        cancelling = client.post('/v1/batches/' + job['id'] + '/cancel', headers=headers).json()
        assert cancelling['status'] == 'cancelling' and cancelling['counts']['cancelled'] == 1
        release.set()
        await task
    asyncio.run(scenario())
    complete = client.get('/v1/batches/' + job['id'], headers=headers).json()
    assert complete['status'] == 'cancelled'
    assert complete['counts']['completed'] == complete['counts']['cancelled'] == 1
    assert not asyncio.run(batch_worker.process_one())


def test_shutdown_requeues_and_expired_claim_reuses_history_without_double_count(client, monkeypatch):
    headers, user_id = account(client)
    job, _ = create(client, headers, ('Phone',))
    async def scenario():
        started = asyncio.Event()
        async def waiting(fields):
            started.set()
            await asyncio.Event().wait()
        monkeypatch.setattr(batch_worker, 'run_analysis', waiting)
        task = asyncio.create_task(batch_worker.process_one())
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())
    assert client.get('/v1/batches/' + job['id'], headers=headers).json()['rows'][0]['status'] == 'queued'
    with SessionLocal() as db:
        item = db.query(AnalysisBatchItem).filter_by(batch_id=job['id']).one()
        user = db.get(User, user_id)
        saved_id = record_analysis(db, user, result(json.loads(item.fields_json)), client_id='batch:' + item.id, commit=False)
        consume_analysis(db, user, commit=False)
        item.status, item.started_at = 'running', now() - timedelta(seconds=batch_worker.LEASE_SECONDS + 5)
        db.get(AnalysisBatch, job['id']).status = 'running'
        db.commit()
    async def forbidden(fields):
        pytest.fail('Do not call the provider twice for saved work')
    monkeypatch.setattr(batch_worker, 'run_analysis', forbidden)
    asyncio.run(batch_worker.process_one())
    complete = client.get('/v1/batches/' + job['id'], headers=headers).json()
    assert complete['rows'][0]['analysis_id'] == saved_id
    assert client.get('/v1/account/me', headers=headers).json()['entitlement']['used'] == 1
    assert len(client.get('/v1/history', headers=headers).json()['items']) == 1


def test_export_prevents_formula_text_and_preserves_empty_prices(client, monkeypatch):
    headers, _ = account(client)
    job, _ = create(client, headers, ('=SUM(1+1)',))
    async def analysis(fields):
        return result(fields, reliable=False)
    monkeypatch.setattr(batch_worker, 'run_analysis', analysis)
    asyncio.run(batch_worker.process_one())
    exported = client.get('/v1/batches/' + job['id'] + '/export', headers=headers)
    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.content.decode('utf-8-sig')), delimiter=';'))
    assert rows[0]['product_name'].startswith("'=")
    assert rows[0]['recommended_price_brl'] == '' and rows[0]['quality'] == 'unavailable'


def test_finished_batch_can_be_deleted_without_removing_history(client, monkeypatch):
    headers, _ = account(client)
    job, _ = create(client, headers, ('Phone',))
    assert client.delete('/v1/batches/' + job['id'], headers=headers).status_code == 409
    async def analysis(fields):
        return result(fields)
    monkeypatch.setattr(batch_worker, 'run_analysis', analysis)
    asyncio.run(batch_worker.process_one())
    other, _ = account(client)
    assert client.delete('/v1/batches/' + job['id'], headers=other).status_code == 404
    assert client.delete('/v1/batches/' + job['id'], headers=headers).status_code == 200
    assert client.get('/v1/batches/' + job['id'], headers=headers).status_code == 404
    assert len(client.get('/v1/history', headers=headers).json()['items']) == 1
