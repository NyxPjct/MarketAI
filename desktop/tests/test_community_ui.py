from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_login_gate_is_primary_screen():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'id="authGate"' in html
    assert 'id="appShell" hidden' in html
    assert html.index('id="authGate"') < html.index('id="appShell"')
    assert "100% GRATUITO" in html
    assert "OPEN SOURCE" in html
    assert "DADOS REAIS" in html


def test_paid_ui_is_not_present():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert 'id="plansCard"' not in html
    assert 'id="billingCountry"' not in html
    assert "buyPlan(" not in js
    assert "activateLicense" not in js
    assert "cancelSubscription" not in js


def test_local_history_is_scoped_by_account():
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert "function accountStorageKey" in js
    assert "nextAccount=String(u.id||u.email||'account')" in js
    assert "activeAccountId=nextAccount" in js
    assert "localStorage.getItem('marketai-history')" not in js
    assert "localStorage.getItem('marketai-watch')" not in js


def test_versioned_installer_configuration():
    version = (ROOT / "backend" / "version.py").read_text(encoding="utf-8")
    iss = (ROOT / "installer" / "MarketAI.iss").read_text(encoding="utf-8")
    assert 'APP_VERSION = "1.0.5"' in version
    assert '#define MyAppVersion "1.0.5"' in iss
    assert 'OutputBaseFilename=MarketAI-Setup-v{#MyAppVersion}' in iss


def test_hidden_attribute_wins_over_layout_css():
    css = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
    assert "[hidden]{display:none!important}" in css
    assert ".auth-gate[hidden],.app-shell[hidden],.app-modal[hidden]{display:none!important}" in css


def test_marketai_confirmation_modal_exists():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert 'id="appModal"' in html
    assert "function openAppModal" in js
    assert "Conta criada" in js or "CONTA CRIADA" in js


def test_monochrome_market_theme():
    css = (ROOT / "frontend" / "style.css").read_text(encoding="utf-8")
    assert "--bg:#050505" in css
    assert "--green:#f5f5f5" in css
    assert "Monochrome Market Theme" in css


def test_multilingual_i18n_bundle_is_loaded_before_app():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    i18n = (ROOT / "frontend" / "i18n.js").read_text(encoding="utf-8")
    assert '<html lang="en">' in html
    assert html.index('/static/i18n.js') < html.index('/static/app.js')
    assert 'data-language-select' in html
    assert "localStorage.getItem(STORAGE_KEY)" in i18n
    assert "current = 'en'" in i18n
    for code in ["en", "pt-BR", "de", "es", "fr"]:
        assert code in i18n


def test_language_switch_covers_primary_auth_copy():
    i18n = (ROOT / "frontend" / "i18n.js").read_text(encoding="utf-8")
    phrases = [
        "Market intelligence. No noise.",
        "Inteligência de mercado. Sem ruído.",
        "Marktintelligenz. Ohne Rauschen.",
        "Inteligencia de mercado. Sin ruido.",
        "Intelligence de marché. Sans bruit.",
    ]
    for phrase in phrases:
        assert phrase in i18n


def test_app_uses_selected_locale_for_dates_and_currency():
    js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")
    assert "const appLocale" in js
    assert "new Intl.NumberFormat(appLocale()" in js
    assert "toLocaleString('pt-BR')" not in js
    assert "toLocaleDateString('pt-BR')" not in js
