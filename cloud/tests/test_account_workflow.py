from datetime import datetime, timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.models import MarketSnapshot


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    monkeypatch.delenv('OPENAI_COPILOT_MODEL', raising=False)
    with TestClient(app) as c:
        yield c


def account(client):
    credentials = {'email': f'{uuid4().hex}@example.com', 'password': 'WorkflowTest123!', 'accept_terms': True}
    response = client.post('/v1/auth/register', json=credentials)
    assert response.status_code == 200
    headers = {'Authorization': 'Bearer ' + response.json()['access_token']}
    assert client.post('/v1/devices/activate', headers=headers, json={'device_uuid': 'workflow-device'}).status_code == 200
    return headers, credentials


def saved_analysis(client, headers, monkeypatch):
    async def fake(fields, image_bytes=None, image_content_type=None):
        return {'product': {'product_name': fields['product_name']}, 'request': fields,
                'market': {'reliable': True, 'checked_at': '2026-01-11T00:00:00Z', 'raw_count': 5,
                           'matched_count': 4, 'pricing_count': 3, 'discarded_count': 2,
                           'quality': {'state': 'reliable', 'minimum_required': 3},
                           'discarded': [{'rejection_reason': 'variant'}, {'rejection_reason': 'outlier'}]},
                'pricing': {'costs': {'unit_cost': 50, 'minimum_for_target_margin': 75, 'desired_margin_percent': 20, 'variable_rate_percent': 15},
                            'strategies': {'recommended': {'price': 100, 'net_profit': 35, 'net_margin_percent': 35}},
                            'opportunity': {'score': 80}, 'market': {'median': 100}}}
    monkeypatch.setattr('app.main.run_analysis', fake)
    response = client.post('/v1/analysis', headers={**headers, 'x-device-id': 'workflow-device'}, data={'product_name': 'Test product'})
    assert response.status_code == 200, response.text
    return response.json()


def test_history_shared_between_devices_and_private_between_accounts(client, monkeypatch):
    owner, credentials = account(client)
    other, _ = account(client)
    result = saved_analysis(client, owner, monkeypatch)
    second = {'Authorization': 'Bearer ' + client.post('/v1/auth/login', json=credentials).json()['access_token']}
    items = client.get('/v1/history', headers=second).json()['items']
    assert len(items) == 1 and items[0]['id'] == result['history_id']
    assert not items[0]['imported']
    assert client.get('/v1/history/' + items[0]['id'], headers=second).json()['analysis']['pricing']['strategies']['recommended']['net_profit'] == 35
    assert client.get('/v1/history', headers=other).json()['items'] == []
    assert client.get('/v1/history/' + items[0]['id'], headers=other).status_code == 404
    assert client.get('/v1/history').status_code == 401
    client.delete('/v1/history', headers=other)
    assert len(client.get('/v1/history', headers=owner).json()['items']) == 1
    client.delete('/v1/history', headers=second)
    assert client.get('/v1/history', headers=owner).json()['items'] == []


def test_import_is_idempotent_and_not_verified_evidence(client):
    owner, _ = account(client)
    item = {'client_id': str(uuid4()), 'date': '2026-01-01T12:00:00-03:00', 'name': 'Legacy product', 'recommended': 9000, 'score': 100}
    for _ in range(2):
        response = client.post('/v1/history/import', headers=owner, json={'items': [item]})
        assert response.status_code == 200 and len(response.json()['items']) == 1
    row = response.json()['items'][0]
    assert row['date'] == '2026-01-01T15:00:00+00:00'
    assert row['imported']
    assert client.get('/v1/history/' + row['id'], headers=owner).json()['analysis'] is None
    answer = client.post('/v1/intelligence/copilot', headers=owner, json={'question': 'Qual a margem?', 'language': 'pt-BR'}).json()
    assert '9000' not in answer['answer'] and answer['context']['analysis'] is None
    for bad in [{**item, 'client_id': 'invalid'}, {**item, 'score': 999}]:
        assert client.post('/v1/history/import', headers=owner, json={'items': [bad]}).status_code == 422


def test_watch_sync_deduplication_and_scoped_clear(client):
    owner, credentials = account(client)
    other, _ = account(client)
    payload = {'product_name': 'Phone', 'variant_text': '128GB', 'purchase_cost': 50}
    watch = client.post('/v1/intelligence/watches', headers=owner, json=payload).json()
    assert client.post('/v1/intelligence/watches', headers=owner, json=payload).json()['id'] == watch['id']
    second = {'Authorization': 'Bearer ' + client.post('/v1/auth/login', json=credentials).json()['access_token']}
    assert client.get('/v1/intelligence/watches', headers=second).json()['items'][0]['id'] == watch['id']
    client.delete('/v1/intelligence/watches', headers=other)
    assert client.get('/v1/intelligence/watches', headers=owner).json()['items'][0]['active']
    assert client.get('/v1/intelligence/forecast/' + watch['id'], headers=other).status_code == 404
    assert client.post('/v1/intelligence/copilot', headers=other, json={'question': 'forecast', 'watch_id': watch['id']}).status_code == 404
    client.delete('/v1/intelligence/watches', headers=second)
    assert not client.get('/v1/intelligence/watches', headers=owner).json()['items'][0]['active']


def test_forecast_endpoint_passes_dates_to_regression(client):
    owner, _ = account(client)
    watch = client.post('/v1/intelligence/watches', headers=owner, json={'product_name': 'Dated product'}).json()
    user_id = client.get('/v1/account/me', headers=owner).json()['user']['id']
    with SessionLocal() as db:
        for day, price in [(1, 100), (2, 110), (11, 200)]:
            db.add(MarketSnapshot(watch_id=watch['id'], user_id=user_id, market_median=price, created_at=datetime(2026, 1, day, tzinfo=timezone.utc)))
        db.commit()
    assert client.get('/v1/intelligence/forecast/' + watch['id'], headers=owner).json()['forecast']['7'] == 270
    answer = client.post('/v1/intelligence/copilot', headers=owner, json={'question': 'Previsão', 'watch_id': watch['id'], 'language': 'pt-BR'}).json()
    assert answer['intents'] == ['forecast']
    assert '270.00' in answer['answer'] and 'preliminar' in answer['answer']


def test_copilot_uses_saved_evidence_and_addresses_question(client, monkeypatch):
    owner, _ = account(client)
    other, _ = account(client)
    result = saved_analysis(client, owner, monkeypatch)
    question = {'question': 'Qual a margem e o custo?', 'analysis_id': result['history_id'], 'language': 'pt-BR', 'analysis': {'price': 99999}}
    answer = client.post('/v1/intelligence/copilot', headers=owner, json=question).json()
    assert answer['mode'] == 'deterministic' and answer['intents'] == ['margin', 'costs']
    assert '35.00%' in answer['answer'] and 'BRL 50.00' in answer['answer']
    assert '99999' not in answer['answer']
    assert answer['evidence_used'] == [{'type': 'analysis', 'id': result['history_id']}]
    assert client.post('/v1/intelligence/copilot', headers=other, json=question).status_code == 404
    unsupported = client.post('/v1/intelligence/copilot', headers=owner, json={'question': 'What is the weather?'}).json()
    assert unsupported['intents'] == [] and 'margin' in unsupported['answer']


def test_evidence_exposes_calculation_counts_and_cost_floor(client, monkeypatch):
    owner, _ = account(client)
    evidence = saved_analysis(client, owner, monkeypatch)['evidence']
    assert evidence['counts'] == {'found': 5, 'compatible': 4, 'used': 3, 'discarded': 2}
    assert evidence['discard_reasons'] == {'variant': 1, 'outlier': 1}
    assert evidence['cost_floor'] == 75 and evidence['recommendation_available']
    assert evidence['collected_at'] == '2026-01-11T00:00:00Z'


@pytest.mark.parametrize('language,phrase', [('en','Declared costs'),('pt-BR','Custos informados'),('de','Angegebene Kosten'),('es','Costes declarados'),('fr','Coûts déclarés')])
def test_copilot_fallback_localizes_evidence(client, monkeypatch, language, phrase):
    owner, _ = account(client)
    result = saved_analysis(client, owner, monkeypatch)
    answer = client.post('/v1/intelligence/copilot', headers=owner, json={'question': 'cost', 'analysis_id': result['history_id'], 'language': language}).json()
    assert phrase in answer['answer']
    assert 'BRL 50.00' in answer['answer']


def test_ai_provider_failure_preserves_useful_deterministic_answer(client, monkeypatch):
    import httpx
    owner, _ = account(client)
    result = saved_analysis(client, owner, monkeypatch)
    monkeypatch.setenv('OPENAI_API_KEY', 'test-only-placeholder')
    monkeypatch.setenv('OPENAI_COPILOT_MODEL', 'test-model')
    async def unavailable(*args, **kwargs):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr('app.intelligence.httpx.AsyncClient.post', unavailable)
    answer = client.post('/v1/intelligence/copilot', headers=owner, json={'question': 'margin', 'analysis_id': result['history_id']}).json()
    assert answer['mode'] == 'deterministic'
    assert answer['fallback_reason'] == 'provider_unavailable'
    assert '35.00%' in answer['answer']
