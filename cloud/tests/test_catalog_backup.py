import copy
import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import CatalogRestore, CatalogRevision
from test_catalog import account, add, selection, save_result


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def export(client, headers):
    response = client.get('/v1/catalog/backup', headers=headers)
    assert response.status_code == 200, response.text
    return response.content


def preview(client, headers, content):
    response = client.post('/v1/catalog/backup/preview', headers=headers, files={'file': ('backup.json', content)})
    assert response.status_code == 200, response.text
    return response.json()


def plan_for(review, rows=None):
    return {'client_id': str(uuid4()), 'digest': review['digest'], 'products': [
        {key: row[key] for key in ['sku', 'expected_id', 'expected_revision', 'expected_watch_id', 'expected_rules_revision']}
        for row in review['items'] if rows is None or row['sku'] in rows]}


def restore(client, headers, content, plan):
    return client.post('/v1/catalog/backup/restore', headers=headers,
                       files={'file': ('backup.json', content)}, data={'plan': json.dumps(plan)})


def edit(client, headers, product, **fields):
    response = client.put('/v1/catalog/'+product['id'], headers=headers, json={
        'fields': {**product['fields'], **fields}, 'stock': 12, 'revision': product['revision']})
    assert response.status_code == 200, response.text
    return response.json()


def test_archive_contains_complete_inputs_revisions_rules_but_no_credentials_or_market_evidence(client):
    headers, user_id = account(client)
    product = add(client, headers)
    product = edit(client, headers, product, purchase_cost=80, supplier_name='Supplier')
    watch = client.post('/v1/catalog/monitor', headers=headers, json=selection(product)).json()['items'][0]['watch_id']
    rule = client.get('/v1/intelligence/watches/'+watch+'/alert-rules', headers=headers).json()
    assert client.put('/v1/intelligence/watches/'+watch+'/alert-rules', headers=headers,
        json={'revision': 0, 'rules': {**rule['rules'], 'minimum_margin_percent': 25}}).status_code == 200
    save_result(user_id, product['fields'])
    archive = json.loads(export(client, headers))
    assert archive['account_id'] == user_id
    saved = archive['products'][0]
    assert saved['fields']['purchase_cost'] == 80 and saved['stock'] == 12
    assert [item['fields']['purchase_cost'] for item in saved['revisions']] == [50, 80]
    assert saved['monitoring_was_active'] and saved['alert_rules']['minimum_margin_percent'] == 25
    assert set(saved) == {'fields','stock','created_at','revisions','monitoring_was_active','alert_rules'}
    assert all(key not in json.dumps(archive) for key in ['access_token','password_hash','recommended_price','payload_json'])
    assert client.get('/v1/catalog/backup').status_code == 401


def test_restore_missing_product_preserves_history_and_rules_pauses_monitor_and_is_retry_safe(client):
    headers, _ = account(client)
    product = edit(client, headers, add(client, headers), purchase_cost=65)
    client.post('/v1/catalog/monitor', headers=headers, json=selection(product))
    content = export(client, headers)
    assert client.delete(f"/v1/catalog/{product['id']}?revision=2", headers=headers).status_code == 200
    review = preview(client, headers, content)
    assert not review['items'][0]['existing']
    plan = plan_for(review)
    response = restore(client, headers, content, plan)
    assert response.status_code == 200, response.text
    assert response.json() == {'created':1,'replaced':0,'revisions':2,'monitoring':'paused'}
    assert restore(client, headers, content, plan).json() == response.json()
    restored = client.get('/v1/catalog', headers=headers).json()['items'][0]
    assert restored['id'] != product['id']
    assert restored['fields']['purchase_cost'] == 65 and restored['stock'] == 12
    assert not restored['monitoring'] and restored['latest'] is None
    changes = client.get('/v1/catalog/'+restored['id']+'/revisions', headers=headers).json()['items']
    assert [row['fields']['purchase_cost'] for row in changes] == [65,50]
    assert all(row['restored'] for row in changes)
    # Re-exporting a restored archive remains valid and retains all revision provenance.
    assert preview(client, headers, export(client, headers))['items'][0]['revisions'] == 2
    assert client.delete(f"/v1/catalog/{restored['id']}?revision=2", headers=headers).status_code == 200


def test_replacing_reviewed_product_keeps_current_history_and_appends_archive_revisions(client):
    headers, _ = account(client)
    product = add(client, headers)
    content = export(client, headers)
    product = edit(client, headers, product, purchase_cost=99)
    review = preview(client, headers, content)
    assert review['items'][0]['existing'] and review['items'][0]['expected_revision'] == 2
    response = restore(client, headers, content, plan_for(review))
    assert response.status_code == 200, response.text
    assert response.json()['replaced'] == 1
    current = client.get('/v1/catalog', headers=headers).json()['items'][0]
    assert current['revision'] == 3 and current['fields']['purchase_cost'] == 50
    history = client.get('/v1/catalog/'+product['id']+'/revisions', headers=headers).json()['items']
    assert [row['fields']['purchase_cost'] for row in history] == [50,99,50]
    assert [row['restored'] for row in history] == [True,False,False]


def test_preview_and_restore_reject_other_accounts_including_edited_preview_refs(client):
    owner, _ = account(client)
    other, _ = account(client)
    add(client, owner)
    content = export(client, owner)
    assert client.post('/v1/catalog/backup/preview', headers=other,
        files={'file': ('backup.json', content)}).status_code == 403
    review = preview(client, owner, content)
    assert restore(client, other, content, plan_for(review)).status_code == 403
    plan = plan_for(review)
    plan['products'][0]['expected_id'] = str(uuid4())
    assert restore(client, owner, content, plan).status_code == 409


def test_restore_detects_edits_and_alert_rule_changes_after_preview(client):
    headers, _ = account(client)
    product = add(client, headers)
    watch = client.post('/v1/catalog/monitor', headers=headers, json=selection(product)).json()['items'][0]['watch_id']
    content = export(client, headers)
    review = preview(client, headers, content)
    settings = client.get('/v1/intelligence/watches/'+watch+'/alert-rules', headers=headers).json()
    assert client.put('/v1/intelligence/watches/'+watch+'/alert-rules', headers=headers,
                      json={'revision':0,'rules':{**settings['rules'],'cooldown_hours':12}}).status_code == 200
    assert restore(client, headers, content, plan_for(review)).status_code == 409
    review = preview(client, headers, content)
    edit(client, headers, product, purchase_cost=90)
    assert restore(client, headers, content, plan_for(review)).status_code == 409


def test_restore_rechecks_file_digest_selection_and_idempotency_key(client):
    headers, _ = account(client)
    add(client, headers, sku='A')
    add(client, headers, sku='B')
    content = export(client, headers)
    review = preview(client, headers, content)
    plan = plan_for(review, ['A'])
    assert restore(client, headers, content+b' ', plan).status_code == 409
    assert restore(client, headers, content, plan).status_code == 200
    plan['products'] = plan_for(preview(client, headers, content), ['B'])['products']
    assert restore(client, headers, content, plan).status_code == 409


def test_restore_is_atomic_when_one_selected_product_changes(client):
    headers, _ = account(client)
    first = add(client, headers, sku='A')
    second = add(client, headers, sku='B')
    content = export(client, headers)
    review = preview(client, headers, content)
    edit(client, headers, second, purchase_cost=101)
    response = restore(client, headers, content, plan_for(review))
    assert response.status_code == 409
    items = client.get('/v1/catalog', headers=headers).json()['items']
    assert [row['revision'] for row in items] == [1,2]
    with SessionLocal() as db:
        assert db.query(CatalogRevision).filter_by(product_id=first['id']).count() == 1


@pytest.mark.parametrize('mutation', [
    lambda data:data.update(version=2),
    lambda data:data['products'][0]['fields'].update(purchase_cost=-1),
    lambda data:data['products'][0]['revisions'][0].update(revision=2),
    lambda data:data['products'][0]['revisions'][0]['fields'].update(purchase_cost=200),
    lambda data:data['products'][0].update(latest={'recommended_price':999}),
    lambda data:data['products'].append(copy.deepcopy(data['products'][0])),
    lambda data:data['products'][0].update(alert_rules={'minimum_margin_percent':-5}),
])
def test_malformed_or_forged_archive_fails_before_mutation(client, mutation):
    headers, _ = account(client)
    add(client, headers)
    data = json.loads(export(client, headers))
    mutation(data)
    response = client.post('/v1/catalog/backup/preview', headers=headers,
        files={'file': ('backup.json', json.dumps(data).encode())})
    assert response.status_code == 422


def test_size_limits_are_explicit_and_exports_never_silently_truncate(client, monkeypatch):
    from app import catalog_backup
    headers, _ = account(client)
    add(client, headers, sku='A');add(client, headers, sku='B')
    monkeypatch.setattr(catalog_backup, 'MAX_PRODUCTS', 1)
    assert client.get('/v1/catalog/backup', headers=headers).status_code == 413
    monkeypatch.setattr(catalog_backup, 'MAX_BACKUP_BYTES', 20)
    assert client.post('/v1/catalog/backup/preview', headers=headers,
        files={'file':('big.json',b'x'*21)}).status_code == 413
