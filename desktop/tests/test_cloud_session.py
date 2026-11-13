import asyncio
import copy

import httpx

from backend.services import cloud


def setup_session(monkeypatch):
    state={'access_token':'old-access','refresh_token':'old-refresh','account':{'id':'account'}}
    monkeypatch.setattr(cloud,'load_cloud_session',lambda:copy.deepcopy(state))
    def save(value):state.clear();state.update(value)
    monkeypatch.setattr(cloud,'save_cloud_session',save)
    monkeypatch.setattr(cloud,'clear_cloud_session',state.clear)
    monkeypatch.setattr(cloud,'_refresh_lock',asyncio.Lock())
    monkeypatch.setattr(cloud,'_session_epoch',0)
    monkeypatch.setattr(cloud,'device_uuid',lambda:'test-device')
    return state


def transport(monkeypatch, handler):
    factory=httpx.AsyncClient
    monkeypatch.setattr(cloud.httpx,'AsyncClient',lambda **kwargs:factory(transport=httpx.MockTransport(handler),**kwargs))


def test_concurrent_expired_requests_refresh_only_once(monkeypatch):
    state=setup_session(monkeypatch);calls=[]
    async def handle(request):
        if request.url.path.endswith('/refresh'):
            calls.append('refresh');await asyncio.sleep(.01)
            return httpx.Response(200,json={'access_token':'new-access','refresh_token':'new-refresh'})
        if request.headers.get('authorization')=='Bearer old-access':return httpx.Response(401)
        return httpx.Response(200,json={'user':{'id':'account'}})
    transport(monkeypatch,handle)
    async def run():return await asyncio.gather(*[cloud.request('GET','/v1/account/me') for _ in range(4)])
    assert all(r.status_code==200 for r in asyncio.run(run()))
    assert calls==['refresh'] and state['refresh_token']=='new-refresh'


def test_temporary_refresh_failure_keeps_session(monkeypatch):
    state=setup_session(monkeypatch)
    def handle(request):return httpx.Response(503 if request.url.path.endswith('/refresh') else 401)
    transport(monkeypatch,handle)
    result=asyncio.run(cloud.account_status())
    assert result['temporary_unavailable'] and state['refresh_token']=='old-refresh'


def test_status_does_not_restore_old_tokens_after_refresh(monkeypatch):
    state=setup_session(monkeypatch)
    def handle(request):
        if request.url.path.endswith('/refresh'):return httpx.Response(200,json={'access_token':'new-access','refresh_token':'new-refresh'})
        if request.headers.get('authorization')=='Bearer old-access':return httpx.Response(401)
        return httpx.Response(200,json={'user':{'id':'account'}})
    transport(monkeypatch,handle)
    assert asyncio.run(cloud.account_status())['authenticated']
    assert state['refresh_token']=='new-refresh'


def test_logout_during_refresh_cannot_resurrect_session(monkeypatch):
    state=setup_session(monkeypatch)
    async def run():
        entered=asyncio.Event();release=asyncio.Event()
        async def handle(request):
            if request.url.path.endswith('/refresh'):
                entered.set();await release.wait()
                return httpx.Response(200,json={'access_token':'new','refresh_token':'new'})
            return httpx.Response(200)
        transport(monkeypatch,handle)
        task=asyncio.create_task(cloud._refresh());await entered.wait()
        await cloud.logout();release.set();assert await task is None
    asyncio.run(run());assert state=={}


def test_invalid_refresh_does_clear_session(monkeypatch):
    state=setup_session(monkeypatch)
    transport(monkeypatch,lambda request:httpx.Response(401))
    assert asyncio.run(cloud._refresh()) is None
    assert state=={}


def test_local_updates_use_public_metadata_without_sending_account_tokens(monkeypatch):
    setup_session(monkeypatch)
    monkeypatch.setenv('MARKETAI_LOCAL_MODE','1')
    def handle(request):
        assert str(request.url)==cloud.PUBLIC_UPDATE_MANIFEST
        assert 'authorization' not in request.headers
        assert 'x-device-id' not in request.headers
        return httpx.Response(200,json={'available':True,'version':'1.6.0'})
    transport(monkeypatch,handle)
    assert asyncio.run(cloud.latest_update()).json()['version']=='1.6.0'
