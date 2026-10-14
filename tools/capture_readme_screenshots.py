from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000"
OUT = Path("docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)

VERSION = "v1.0.5"


def set_demo_account(page):
    page.evaluate("""
    () => {
      localStorage.setItem('marketai-language', 'en');
      if (window.MarketI18n) window.MarketI18n.setLanguage('en');
      const gate = document.querySelector('#authGate');
      const shell = document.querySelector('#appShell');
      if (gate) gate.hidden = true;
      if (shell) shell.hidden = false;
      document.body.classList.add('is-authenticated');
      const values = {
        accountName: 'MarketAI User',
        accountEmail: 'user@example.com',
        accountPlan: 'COMMUNITY',
        accountRemaining: 'FREE',
        accountQuota: 'UNLIMITED',
        accountStatus: 'ACTIVE',
        apiStatus: 'Community · ONLINE',
        appVersion: 'MarketAI v1.0.5'
      };
      for (const [id, value] of Object.entries(values)) {
        const el = document.getElementById(id);
        if (el) el.textContent = value;
      }
      const modal = document.querySelector('#appModal');
      if (modal) modal.hidden = true;
      if (window.MarketI18n) window.MarketI18n.refresh();
    }
    """)


def wait_english(page):
    page.wait_for_function("""
    () => document.documentElement.lang === 'en'
      && document.body.innerText.includes('Market intelligence. No noise.')
      && !document.body.innerText.includes('Inteligência de mercado. Sem ruído.')
    """)


def open_view(page, view):
    set_demo_account(page)
    button = page.locator(f'[data-view="{view}"]')
    if button.count():
        button.first.click()
    page.wait_for_timeout(250)
    if page.locator('[data-language-select]').count():
        assert page.locator('[data-language-select]').first.input_value() == 'en'


def shot(page, name):
    page.screenshot(path=str(OUT / name), full_page=False)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(
        viewport={"width": 1600, "height": 900},
        device_scale_factor=1,
        locale="en-US",
    )
    context.add_init_script("localStorage.setItem('marketai-language','en')")

    # Validate all supported languages before capturing the English README set.
    check = context.new_page()
    check.goto(BASE_URL, wait_until="networkidle")
    wait_english(check)
    expected = {
        "en": {
            "hero": "Market intelligence. No noise.",
            "nav": "New analysis",
            "main": "Know whether it is worth selling before you buy.",
            "product": "Product",
            "intel": "Your commercial command center.",
        },
        "pt-BR": {
            "hero": "Inteligência de mercado. Sem ruído.",
            "nav": "Nova análise",
            "main": "Descubra se vale a pena vender antes de comprar.",
            "product": "Produto",
            "intel": "Seu centro de comando comercial.",
        },
        "de": {
            "hero": "Marktintelligenz. Ohne Rauschen.",
            "nav": "Neue Analyse",
            "main": "Erkenne vor dem Einkauf, ob sich der Verkauf lohnt.",
            "product": "Produkt",
            "intel": "Deine kommerzielle Kommandozentrale.",
        },
        "es": {
            "hero": "Inteligencia de mercado. Sin ruido.",
            "nav": "Nuevo análisis",
            "main": "Descubre si vale la pena vender antes de comprar.",
            "product": "Producto",
            "intel": "Tu centro de mando comercial.",
        },
        "fr": {
            "hero": "Intelligence de marché. Sans bruit.",
            "nav": "Nouvelle analyse",
            "main": "Découvrez si la vente vaut le coup avant d’acheter.",
            "product": "Produit",
            "intel": "Votre centre de commande commercial.",
        },
    }
    for code, phrases in expected.items():
        check.evaluate("(code) => window.MarketI18n.setLanguage(code)", code)
        check.wait_for_function("(phrase) => document.body.innerText.includes(phrase)", arg=phrases["hero"])
        assert check.locator("[data-language-select]").first.input_value() == code
        assert check.locator('[data-view="analyze"] span').text_content().strip() == phrases["nav"]
        assert check.locator("main > .topbar h1").text_content().strip() == phrases["main"]
        assert check.locator("#view-analyze .form-card h2").first.text_content().strip() == phrases["product"]
        assert check.locator("#view-intelligence .intel-hero h2").text_content().strip() == phrases["intel"]
    check.evaluate("() => window.MarketI18n.setLanguage('en')")
    wait_english(check)
    check.close()

    # Login
    page = context.new_page()
    page.goto(BASE_URL, wait_until="networkidle")
    wait_english(page)
    page.locator("#cloudEmail").fill("user@example.com")
    page.locator("#cloudPassword").fill("MarketAI123")
    page.wait_for_timeout(180)
    shot(page, "01-login-community-v1.0.5.png")
    page.close()

    # Dashboard / New analysis
    page = context.new_page()
    page.goto(BASE_URL, wait_until="networkidle")
    wait_english(page)
    open_view(page, "analyze")
    shot(page, "02-dashboard-v1.0.5.png")
    page.close()

    # Intelligence Core
    page = context.new_page()
    page.goto(BASE_URL, wait_until="networkidle")
    wait_english(page)
    open_view(page, "intelligence")
    shot(page, "03-intelligence-core-v1.0.5.png")
    page.close()

    # My account
    page = context.new_page()
    page.goto(BASE_URL, wait_until="networkidle")
    wait_english(page)
    open_view(page, "account")
    set_demo_account(page)
    page.wait_for_timeout(150)
    shot(page, "04-my-account-v1.0.5.png")
    page.close()

    # Settings
    page = context.new_page()
    page.goto(BASE_URL, wait_until="networkidle")
    wait_english(page)
    open_view(page, "settings")
    shot(page, "05-settings-v1.0.5.png")
    page.close()

    # Account-created modal
    page = context.new_page()
    page.goto(BASE_URL, wait_until="networkidle")
    wait_english(page)
    open_view(page, "analyze")
    page.evaluate("""
    () => {
      window.openAppModal({
        eyebrow: 'ACCOUNT CREATED',
        title: 'Welcome to MarketAI.',
        message: 'Your account user@example.com was created successfully. All Community features are unlocked for free.',
        symbol: '✓',
        button: 'ENTER MARKETAI'
      });
      if (window.MarketI18n) window.MarketI18n.refresh();
    }
    """)
    page.wait_for_timeout(180)
    shot(page, "06-account-created-modal-v1.0.5.png")
    page.close()

    context.close()
    browser.close()

shots = sorted(OUT.glob("*v1.0.5.png"))
assert len(shots) == 6, f"Expected 6 v1.0.5 screenshots, got {len(shots)}"
print("English README screenshots generated:", len(shots))
