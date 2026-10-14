"""Browser regression for the account workflow using isolated synthetic market data.

Requires Playwright in the controller Python and a Chromium executable.
--python selects Python with the repository's Cloud/Desktop dependencies.
No live providers are contacted; all databases and credentials are disposable.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import httpx
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[1]

CLOUD_FIXTURE = '''import sys, os
sys.path.insert(0,os.environ['WORKFLOW_CLOUD_ROOT'])
import app.market_engine as market
from app.main import app
import uvicorn

async def identity(name,variant,*args):
    return {'product_name':name,'brand':'Apple','model':'iPhone 16','category':'smartphone','confidence':90,'variant_summary':'128GB'}

async def source(query,**kwargs):
    items=[{'source':'Mercado Livre Brasil','title':'Apple iPhone 16 128GB Novo','price':price,'currency':'BRL',
            'url':f'https://example.com/item/{index}','condition':'new','metadata':{'seller_nickname':f'Seller {index}'}}
           for index,price in enumerate([100,110,120,125])]
    return {'items':items,'diagnostic':{'source':'Mercado Livre Brasil','status':'ok','returned':len(items),'checked_at':'2026-01-11T00:00:00Z'}}

async def unavailable(*args,**kwargs):
    return {'items':[],'diagnostic':{'source':'Google Shopping','status':'not_configured','returned':0}}
market.identify_product=identity
market.search_mercado_livre_live=source
market.search_google_shopping_live=unavailable
uvicorn.run(app,host='127.0.0.1',port=int(os.environ['WORKFLOW_CLOUD_PORT']))
'''

def check_workflow(desktop_a, desktop_b, db_path, chromium):
    password=secrets.token_urlsafe(24)
    credentials={'email':f'browser-{uuid.uuid4().hex}@example.com','password':password,'full_name':'Workflow test'}
    r=httpx.post(desktop_a+'/api/cloud/register',json=credentials);r.raise_for_status();uid=r.json()['user']['id']
    r=httpx.post(desktop_b+'/api/cloud/login',json=credentials);r.raise_for_status()
    errors=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(executable_path=chromium,headless=True,args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':1440,'height':1000})
        a=context.new_page();a.on('pageerror',lambda error:errors.append(str(error)))
        a.goto(desktop_a)
        expect(a.locator('#appShell')).to_be_visible()
        expect(a.locator('#historySyncStatus')).to_have_text('Synced with your account.')
        # Legacy data migrates once and is labeled as an imported summary.
        a.evaluate('(uid)=>{localStorage.removeItem(`marketai-history-migrated:${uid}`);localStorage.setItem(`marketai-history:${uid}`,JSON.stringify([{name:"Imported legacy",date:"2026-01-01T12:00:00Z",recommended:90,score:50,marketMedian:100,mode:"reliable"}]))}',uid)
        a.evaluate('syncAccountData(true)')
        assert httpx.get(desktop_a+'/api/history').json()['items'][0]['imported']
        a.locator('[name=product_name]').fill('Apple iPhone 16')
        a.locator('[name=variant_text]').fill('128GB')
        a.locator('[name=purchase_cost]').fill('50')
        a.locator('[name=purchase_currency]').select_option('BRL')
        a.locator('[name=destination_country]').select_option('BR')
        a.locator('#analysisForm [type=submit]').click()
        expect(a.locator('#result')).to_be_visible(timeout=20000)
        expect(a.locator('#qualityBadge')).to_have_text('APPROVED FOR PRICING')
        expect(a.locator('#evidenceSummary')).to_contain_text('listings used')
        a.locator('#compareMargin').click()
        assert a.locator('#priceSlider').evaluate('(el)=>el===document.activeElement')
        a.locator('#saveWatch').click()
        expect(a.locator('#monitorFeedback')).to_contain_text('Saved to your account.')
        expect(a.locator('#workflowSteps [data-step=monitor]')).to_have_attribute('aria-current','step')
        a.locator('#saveWatch').click()
        expect(a.locator('#monitorFeedback')).to_contain_text('Saved to your account.')
        watches=httpx.get(desktop_a+'/api/intelligence/watches').json()['items'];assert len(watches)==1
        watch=watches[0]['id']
        db=sqlite3.connect(db_path)
        for day,price in [(1,100),(2,110),(11,200)]:
            db.execute('INSERT INTO market_snapshots (id,watch_id,user_id,market_median,listing_count,quality_score,payload_json,created_at) VALUES (?,?,?,?,?,?,?,?)',
                       (str(uuid.uuid4()),watch,uid,price,4,80,'{}',f'2026-01-{day:02d} 00:00:00.000000'))
        db.commit();db.close()
        # Second device sees the same analysis and monitored product.
        b=browser.new_context().new_page();b.on('pageerror',lambda error:errors.append(str(error)))
        b.goto(desktop_b);expect(b.locator('#appShell')).to_be_visible()
        expect(b.locator('#historySyncStatus')).to_have_text('Synced with your account.')
        b.locator('[data-view=history]').click()
        expect(b.locator('#historyList')).to_contain_text('Apple iPhone 16')
        expect(b.locator('#historyList')).to_contain_text('Imported summary')
        b.locator('.reopen-analysis').first.click();expect(b.locator('#result')).to_be_visible()
        b.locator('[data-view=intelligence]').click()
        expect(b.locator('#forecastTarget option')).to_have_count(2)
        b.locator('#forecastTarget').select_option(watch);b.locator('#loadForecast').click()
        expect(b.locator('#forecastOutput')).to_contain_text('270.00')
        expect(b.locator('#forecastOutput')).to_contain_text('Preliminary estimate')
        b.locator('#copilotQuestion').fill('What is the margin and cost?');b.locator('#askCopilot').click()
        expect(b.locator('#copilotMode')).to_contain_text('Deterministic response')
        expect(b.locator('#copilotAnswer')).to_contain_text('Unit cost: BRL 50.00')
        for language in ['pt-BR','de','es','fr','en']:
            b.evaluate('(lang)=>window.MarketI18n.setLanguage(lang)',language)
            expect(b.locator('html')).to_have_attribute('lang',language)
            assert b.locator('#loadForecast').inner_text() != 'View forecast' or language=='en'
        # A failed refresh preserves the local cache and explicitly reports it.
        b.evaluate('syncAccountData(true)')
        b.route('**/api/history',lambda route:route.abort())
        b.locator('[data-view=history]').click()
        b.locator('#refreshHistory').click()
        expect(b.locator('#historySyncStatus')).to_contain_text('Offline or sync failed')
        expect(b.locator('#historyList')).to_contain_text('Apple iPhone 16')
        b.unroute('**/api/history')
        # Clear from device B, refresh A: deleted items must not be re-imported.
        b.on('dialog',lambda dialog:dialog.accept())
        b.locator('#clearHistory').click()
        expect(b.locator('#historyList .history-item')).to_have_count(0)
        a.evaluate('syncAccountData(true)')
        assert httpx.get(desktop_a+'/api/history').json()['items']==[]
        b.locator('[data-view=watchlist]').click();b.locator('#clearWatchlist').click()
        expect(b.locator('#watchList .watch-item')).to_have_count(0)
        a.evaluate('syncAccountData(true)')
        assert not any(x['active'] for x in httpx.get(desktop_a+'/api/intelligence/watches').json()['items'])
        # Missing market evidence leaves the cost simulator available, with a guided retry.
        a.locator('#newAnalysis').click();a.locator('[name=destination_country]').select_option('CA')
        a.locator('#analysisForm [type=submit]').click();expect(a.locator('#result')).to_be_visible()
        expect(a.locator('#recommendedPrice')).to_have_text('BLOCKED')
        expect(a.locator('#nextActionMessage')).to_contain_text('No source returned market data')
        b.locator('[data-view=account]').click();b.locator('#cloudLogout').click()
        expect(b.locator('#authGate')).to_be_visible()
        assert b.evaluate('currentAnalysis===null')
        assert not errors,errors
        browser.close()


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


@contextmanager
def services(python):
    with tempfile.TemporaryDirectory(prefix='marketai-workflow-') as temp:
        directory = Path(temp)
        db_path = directory / 'cloud.db'
        ports = [free_port() for _ in range(3)]
        fixture = directory / 'cloud_fixture.py'
        fixture.write_text(CLOUD_FIXTURE, encoding='utf-8')
        env = dict(os.environ)
        for name in ('OPENAI_API_KEY', 'MERCADOLIVRE_ACCESS_TOKEN', 'EBAY_CLIENT_ID', 'EBAY_CLIENT_SECRET',
                     'SERPAPI_KEY', 'ADMIN_EMAIL', 'ADMIN_PASSWORD', 'ADMIN_API_KEY'):
            env.pop(name, None)
        env.update(DATABASE_URL='sqlite:///' + str(db_path), WORKFLOW_CLOUD_ROOT=str(ROOT / 'cloud'),
                   WORKFLOW_CLOUD_PORT=str(ports[0]))
        processes = []
        logs = []
        try:
            targets = [([python, str(fixture)], ROOT / 'cloud', '/health')]
            for port in ports[1:]:
                targets.append(([python, '-m', 'uvicorn', 'backend.main:app', '--host', '127.0.0.1', '--port', str(port)], ROOT / 'desktop', '/api/health'))
            for index, (command, cwd, health) in enumerate(targets):
                process_env = dict(env)
                if index:
                    process_env.update(MARKETAI_CLOUD_URL=f'http://127.0.0.1:{ports[0]}',
                                       MARKETAI_DATA_DIR=str(directory / f'device-{index}'))
                log = (directory / f'service-{index}.log').open('w+')
                logs.append(log)
                process = subprocess.Popen(command, cwd=cwd, env=process_env, stdout=log, stderr=subprocess.STDOUT)
                processes.append(process)
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        log.seek(0)
                        raise RuntimeError('Test service failed: ' + log.read())
                    try:
                        if httpx.get(f'http://127.0.0.1:{ports[index]}{health}', timeout=1).status_code == 200:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError('Test service did not become ready')
            yield (f'http://127.0.0.1:{ports[1]}', f'http://127.0.0.1:{ports[2]}', db_path)
        finally:
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for log in logs:
                log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--python', default=sys.executable, help='Python with Cloud/Desktop dependencies')
    parser.add_argument('--chromium', default=shutil.which('chromium'), help='Chromium executable; otherwise use Playwright browser')
    args = parser.parse_args()
    with services(args.python) as (desktop_a, desktop_b, db_path):
        check_workflow(desktop_a, desktop_b, db_path, args.chromium)
    print('PASS: guided analysis, evidence, migration, two-device sync, forecast, Copilot, five languages, offline cache, deletion and logout')


if __name__ == '__main__':
    main()
