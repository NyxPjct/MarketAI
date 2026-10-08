from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_login_gate_is_primary_screen():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    assert 'id="authGate"' in html
    assert 'id="appShell" hidden' in html
    assert html.index('id="authGate"') < html.index('id="appShell"')
    assert "100% GRATUITO" in html
    assert "OPEN SOURCE" in html
    assert "SEM PAYWALL" in html


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
    assert "activeAccountId=String(u.id||u.email||'account')" in js
    assert "localStorage.getItem('marketai-history')" not in js
    assert "localStorage.getItem('marketai-watch')" not in js


def test_versioned_installer_configuration():
    version = (ROOT / "backend" / "version.py").read_text(encoding="utf-8")
    iss = (ROOT / "installer" / "MarketAI.iss").read_text(encoding="utf-8")
    assert 'APP_VERSION = "1.0.2"' in version
    assert '#define MyAppVersion "1.0.2"' in iss
    assert 'OutputBaseFilename=MarketAI-Setup-v{#MyAppVersion}' in iss
