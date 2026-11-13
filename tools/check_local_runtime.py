"""Exercise the embedded service in a disposable directory, including restart."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time
import httpx
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[1]

@contextmanager
def launch(python, directory):
    with socket.socket() as s:
        s.bind(('127.0.0.1',0));port=s.getsockname()[1]
    env=dict(os.environ)
    for key in ['OPENAI_API_KEY','MERCADOLIVRE_ACCESS_TOKEN','EBAY_CLIENT_ID','EBAY_CLIENT_SECRET','SERPAPI_KEY']:
        env.pop(key,None)
    env['MARKETAI_CLOUD_URL']='http://127.0.0.1:9'  # Unreachable remote must not matter.
    # The embedded service must stay local even when a system proxy is configured.
    for name in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','http_proxy','https_proxy','all_proxy']:
        env[name]='http://127.0.0.1:9'
    env['NO_PROXY']=env['no_proxy']=''
    log=(directory/'test-runtime.log').open('w+')
    process=subprocess.Popen([python,'-m','backend.local_runtime','--data-dir',str(directory),'--desktop-port',str(port)],
        cwd=ROOT/'desktop',env=env,stdout=log,stderr=subprocess.STDOUT)
    url=f'http://127.0.0.1:{port}'
    try:
        for _ in range(150):
            if process.poll() is not None:
                log.seek(0);raise RuntimeError(log.read())
            try:
                if httpx.get(url+'/api/health',timeout=1).is_success:break
            except httpx.HTTPError:pass
            time.sleep(.2)
        else:raise RuntimeError('Local app startup timeout')
        yield url
    finally:
        process.terminate()
        try:process.wait(timeout=20)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        log.close()

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--python',required=True);parser.add_argument('--chromium')
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='marketai-local-test-') as tmp:
        directory=Path(tmp)
        (directory/'cloud-session.bin').write_bytes(b'preserve-old-remote-session')
        with launch(args.python,directory) as url:
            status=httpx.get(url+'/api/cloud/status').json()
            assert status['authenticated'] and status['mode']=='local'
            uid=status['user']['id']
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
                page=browser.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(url);expect(page.locator('#appShell')).to_be_visible()
                expect(page.locator('#localModeNotice')).to_be_visible()
                expect(page.locator('#cloudLogout')).not_to_be_visible()
                page.locator('[data-view=catalog]').click();page.locator('#catalogNew').click()
                page.locator('#catalogFields [name=sku]').fill('LOCAL-001')
                page.locator('#catalogFields [name=product_name]').fill('Local product')
                page.locator('#catalogFields [name=purchase_cost]').fill('25')
                page.locator('#catalogFields [name=destination_country]').select_option('CA')
                page.locator('#catalogSave').click();expect(page.locator('#catalogEditor')).not_to_be_visible()
                expect(page.locator('#catalogRows')).to_contain_text('LOCAL-001')
                page.locator('#catalogSelectAll').check();page.locator('#catalogAnalyze').click()
                expect(page.locator('#batchProgress')).to_contain_text('Completed · 1/1',timeout=30000)
                assert httpx.get(url+'/api/history').json()['items']
                with page.expect_download() as download:
                    page.locator('[data-view=catalog]').click();page.locator('#catalogBackupPanel summary').click()
                    page.locator('#catalogBackupExport').click()
                backup=Path(download.value.path()).read_bytes();assert json.loads(backup)['products'][0]['fields']['sku']=='LOCAL-001'
                page.locator('[data-view=settings]').click();expect(page.locator('#localIntegrations')).to_be_visible()
                expect(page.locator('#cloudServices')).not_to_be_visible()
                for lang in ['pt-BR','de','es','fr','en']:
                    page.evaluate('(lang)=>MarketI18n.setLanguage(lang)',lang)
                    assert page.locator('#localModeNotice').inner_text().strip()
                assert not errors,errors
                browser.close()
        with launch(args.python,directory) as url:
            assert httpx.get(url+'/api/cloud/status').json()['user']['id']==uid
            items=httpx.get(url+'/api/catalog').json()['items']
            assert items[0]['fields']['sku']=='LOCAL-001'
            assert httpx.get(url+'/api/history').json()['items']
            assert (directory/'cloud-session.bin').read_bytes()==b'preserve-old-remote-session'
            # User-supplied Cloud archives can migrate inputs into the local profile.
            archive=json.loads(backup);archive['account_id']='00000000-0000-4000-8000-000000000001'
            result=httpx.post(url+'/api/catalog/backup/preview',files={'file':('backup.json',json.dumps(archive).encode())})
            assert result.status_code==200,result.text
            review=result.json()
            from uuid import uuid4
            plan={'client_id':str(uuid4()),'digest':review['digest'],'products':[
                {key:row[key] for key in ['sku','expected_id','expected_revision','expected_watch_id','expected_rules_revision']}
                for row in review['items']]}
            restored=httpx.post(url+'/api/catalog/backup/restore',files={'file':('backup.json',json.dumps(archive).encode())},data={'plan':json.dumps(plan)})
            assert restored.status_code==200,restored.text
            assert restored.json()['replaced']==1
    print('PASS: automatic local profile, SQLite catalog/history, analyses without hosted Cloud, backup export/import, restart persistence, five languages and preserved remote session')

if __name__=='__main__':main()
