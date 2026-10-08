from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000"
OUT = Path("docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)

def set_demo_account(page):
    page.evaluate("""
    () => {
      const gate = document.querySelector('#authGate');
      const shell = document.querySelector('#appShell');
      if (gate) gate.hidden = true;
      if (shell) shell.hidden = false;
      document.body.classList.add('is-authenticated');
      const values = {
        accountName: 'Usuário MarketAI',
        accountEmail: 'usuario@exemplo.com',
        accountPlan: 'COMMUNITY',
        accountRemaining: 'GRÁTIS',
        accountQuota: 'ILIMITADAS',
        accountStatus: 'ATIVO',
        apiStatus: 'Community · ONLINE',
        appVersion: 'MarketAI v1.0.3'
      };
      for (const [id, value] of Object.entries(values)) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
      }
      const onboarding = document.querySelector('#onboarding');
      if (onboarding) onboarding.hidden = true;
      const modal = document.querySelector('#appModal');
      if (modal) modal.hidden = true;
    }
    """)

def open_view(page, view):
    set_demo_account(page)
    button = page.locator(f'[data-view="{view}"]')
    if button.count():
        button.first.click()
    page.wait_for_timeout(250)

def shot(page, name):
    page.screenshot(path=str(OUT / name), full_page=False)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)

    # Login
    page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
    page.goto(BASE_URL, wait_until="networkidle")
    page.locator("#cloudEmail").fill("usuario@exemplo.com")
    page.locator("#cloudPassword").fill("MarketAI123")
    page.wait_for_timeout(200)
    shot(page, "01-login-community-v1.0.3.png")
    page.close()

    # Dashboard / Nova análise
    page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
    page.goto(BASE_URL, wait_until="networkidle")
    open_view(page, "analyze")
    shot(page, "02-dashboard-v1.0.3.png")
    page.close()

    # Intelligence Core
    page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
    page.goto(BASE_URL, wait_until="networkidle")
    open_view(page, "intelligence")
    shot(page, "03-intelligence-core-v1.0.3.png")
    page.close()

    # Minha conta
    page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
    page.goto(BASE_URL, wait_until="networkidle")
    open_view(page, "account")
    set_demo_account(page)
    page.wait_for_timeout(150)
    shot(page, "04-minha-conta-v1.0.3.png")
    page.close()

    # Configurações
    page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
    page.goto(BASE_URL, wait_until="networkidle")
    open_view(page, "settings")
    shot(page, "05-configuracoes-v1.0.3.png")
    page.close()

    # Modal de conta criada
    page = browser.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
    page.goto(BASE_URL, wait_until="networkidle")
    open_view(page, "analyze")
    page.evaluate("""
    () => {
      if (typeof window.openAppModal === 'function') {
        window.openAppModal({
          eyebrow: 'CONTA CRIADA',
          title: 'Bem-vindo ao MarketAI.',
          message: 'Sua conta foi criada com sucesso. Todos os recursos Community estão liberados gratuitamente.',
          symbol: '✓',
          button: 'ENTRAR NO MARKETAI'
        });
      } else {
        const modal = document.querySelector('#appModal');
        if (modal) {
          modal.hidden = false;
          modal.setAttribute('aria-hidden', 'false');
          const title = document.querySelector('#appModalTitle');
          const msg = document.querySelector('#appModalMessage');
          if (title) title.textContent = 'Bem-vindo ao MarketAI.';
          if (msg) msg.textContent = 'Sua conta foi criada com sucesso. Todos os recursos Community estão liberados gratuitamente.';
        }
      }
    }
    """)
    page.wait_for_timeout(180)
    shot(page, "06-conta-criada-modal-v1.0.3.png")
    page.close()

    browser.close()

print("README screenshots generated:", len(list(OUT.glob("*.png"))))
