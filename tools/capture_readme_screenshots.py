import os
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE_URL = "http://127.0.0.1:8000"
OUT = Path("docs/screenshots")
OUT.mkdir(parents=True, exist_ok=True)

VERSION = "v1.2.0"


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
        appVersion: 'MarketAI v1.2.0'
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
    browser = p.chromium.launch(headless=True, executable_path=os.getenv("CHROMIUM_EXECUTABLE") or None)
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
            "account": "YOUR ACCOUNT",
            "settings": "Interface language",
            "modal": "Welcome to MarketAI.",
        },
        "pt-BR": {
            "hero": "Inteligência de mercado. Sem ruído.",
            "nav": "Nova análise",
            "main": "Descubra se vale a pena vender antes de comprar.",
            "product": "Produto",
            "intel": "Seu centro de comando comercial.",
            "account": "SUA CONTA",
            "settings": "Idioma da interface",
            "modal": "Bem-vindo ao MarketAI.",
        },
        "de": {
            "hero": "Marktintelligenz. Ohne Rauschen.",
            "nav": "Neue Analyse",
            "main": "Erkenne vor dem Einkauf, ob sich der Verkauf lohnt.",
            "product": "Produkt",
            "intel": "Deine kommerzielle Kommandozentrale.",
            "account": "DEIN KONTO",
            "settings": "Sprache der Oberfläche",
            "modal": "Willkommen bei MarketAI.",
        },
        "es": {
            "hero": "Inteligencia de mercado. Sin ruido.",
            "nav": "Nuevo análisis",
            "main": "Descubre si vale la pena vender antes de comprar.",
            "product": "Producto",
            "intel": "Tu centro de mando comercial.",
            "account": "TU CUENTA",
            "settings": "Idioma de la interfaz",
            "modal": "Bienvenido a MarketAI.",
        },
        "fr": {
            "hero": "Intelligence de marché. Sans bruit.",
            "nav": "Nouvelle analyse",
            "main": "Découvrez si la vente vaut le coup avant d’acheter.",
            "product": "Produit",
            "intel": "Votre centre de commande commercial.",
            "account": "VOTRE COMPTE",
            "settings": "Langue de l’interface",
            "modal": "Bienvenue sur MarketAI.",
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
        assert check.locator("#view-account .eyebrow").first.text_content().strip() == phrases["account"]
        assert check.locator("#view-settings #settingsLanguage").count() == 1
        assert check.locator("#view-settings .language-settings-card h2").text_content().strip() == phrases["settings"]
        check.evaluate("""() => window.openAppModal({
          eyebrow:'ACCOUNT CREATED',
          title:'Welcome to MarketAI.',
          message:'Your account user@example.com was created successfully. All Community features are unlocked for free.',
          symbol:'✓',
          button:'ENTER MARKETAI'
        })""")
        assert check.locator("#appModalTitle").text_content().strip() == phrases["modal"]
        check.evaluate("() => window.closeAppModal()")
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
    shot(page, "01-login-community-v1.2.0.png")
    page.close()

    # Dashboard / New analysis
    page = context.new_page()
    page.goto(BASE_URL, wait_until="networkidle")
    wait_english(page)
    open_view(page, "analyze")
    shot(page, "02-dashboard-v1.2.0.png")
    page.close()

    # Intelligence Core
    page = context.new_page()
    page.goto(BASE_URL, wait_until="networkidle")
    wait_english(page)
    open_view(page, "intelligence")
    shot(page, "03-intelligence-core-v1.2.0.png")
    page.close()

    # My account
    page = context.new_page()
    page.goto(BASE_URL, wait_until="networkidle")
    wait_english(page)
    open_view(page, "account")
    set_demo_account(page)
    page.wait_for_timeout(150)
    shot(page, "04-my-account-v1.2.0.png")
    page.close()

    # Settings
    page = context.new_page()
    page.goto(BASE_URL, wait_until="networkidle")
    wait_english(page)
    open_view(page, "settings")
    shot(page, "05-settings-v1.2.0.png")
    page.close()

    # Catalog CSV review uses labeled demo inputs, never real market evidence.
    page = context.new_page()
    page.goto(BASE_URL, wait_until="networkidle")
    wait_english(page)
    open_view(page, "batches")
    demo = {
        "rows": [
            {"line":2,"fields":{"sku":"PHONE-128","product_name":"Apple iPhone 16","variant_text":"128 GB","purchase_cost":2500,"purchase_currency":"BRL","destination_country":"BR","marketplace_fee_percent":16,"taxes_percent":6,"ads_percent":3,"desired_margin_percent":20},"valid":True,"errors":[]},
            {"line":3,"fields":{"sku":"PERFUME-100","product_name":"Dior Sauvage","variant_text":"Eau de Parfum 100 ml","purchase_cost":450,"purchase_currency":"BRL","destination_country":"BR","marketplace_fee_percent":16,"taxes_percent":6,"ads_percent":3,"desired_margin_percent":20},"valid":True,"errors":[]}
        ],"valid_count":2,"invalid_count":0,"max_rows":50,"delimiter":";"
    }
    page.route("**/api/batches/preview", lambda route: route.fulfill(json=demo))
    page.locator("#batchFile").set_input_files({"name":"catalog-demo.csv","mimeType":"text/csv","buffer":b"product_name;purchase_cost\nApple iPhone 16;2500\nDior Sauvage;450\n"})
    page.locator("#batchPreviewButton").click()
    page.wait_for_function("document.querySelectorAll('#batchPreviewRows tr').length === 2")
    shot(page, "07-catalog-csv-v1.2.0.png")
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
    shot(page, "06-account-created-modal-v1.2.0.png")
    page.close()

    context.close()
    browser.close()

shots = sorted(OUT.glob("*v1.2.0.png"))
assert len(shots) == 7, f"Expected 7 v1.2.0 screenshots, got {len(shots)}"
print("English README screenshots generated:", len(shots))
