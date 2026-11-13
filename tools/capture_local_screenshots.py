"""Capture the real local UI using a disposable catalog with no market prices."""
import argparse
from pathlib import Path
import tempfile

import httpx
from playwright.sync_api import sync_playwright, expect

from check_local_runtime import launch, ROOT


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--python',required=True)
    parser.add_argument('--chromium')
    args=parser.parse_args()
    output=ROOT/'docs/screenshots'
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='marketai-local-shots-') as tmp:
        with launch(args.python,Path(tmp)) as url:
            response=httpx.post(url+'/api/catalog/import',json={'products':[{
                'fields':{'sku':'EXAMPLE-001','product_name':'Example product',
                          'purchase_cost':25,'supplier_name':'Example supplier'},'stock':3}]})
            response.raise_for_status()
            version=httpx.get(url+'/api/app/info').json()['version']
            with sync_playwright() as p:
                browser=p.chromium.launch(executable_path=args.chromium,headless=True,args=['--no-sandbox'])
                page=browser.new_page(viewport={'width':1600,'height':1000},locale='en-US')
                page.add_init_script("localStorage.setItem('marketai-language','en')")
                page.goto(url)
                expect(page.locator('#appShell')).to_be_visible()
                expect(page.locator('#localModeNotice')).to_be_visible()
                page.locator('[data-view=catalog]').click()
                expect(page.locator('#catalogRows')).to_contain_text('EXAMPLE-001')
                page.screenshot(path=str(output/f'local-catalog-v{version}.png'),full_page=True)
                page.locator('[data-view=settings]').click()
                expect(page.locator('#localIntegrations')).to_be_visible()
                page.screenshot(path=str(output/f'local-settings-v{version}.png'),full_page=True)
                browser.close()


if __name__=='__main__':main()
