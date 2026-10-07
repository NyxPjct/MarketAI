from __future__ import annotations
import os
from dataclasses import dataclass


def _bool(name: str, default=False):
    return os.getenv(name, str(default)).strip().lower() in {"1","true","yes","on"}

@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./marketai-cloud.db")
    jwt_secret: str = os.getenv("JWT_SECRET", "dev-only-change-me")
    access_minutes: int = int(os.getenv("ACCESS_TOKEN_MINUTES", "15"))
    refresh_days: int = int(os.getenv("REFRESH_TOKEN_DAYS", "30"))
    admin_api_key: str = os.getenv("ADMIN_API_KEY", "").strip()
    admin_email: str = os.getenv("ADMIN_EMAIL", "").strip().lower()
    admin_password: str = os.getenv("ADMIN_PASSWORD", "")
    admin_name: str = os.getenv("ADMIN_NAME", "MarketAI Admin")
    admin_panel_enabled: bool = _bool("ADMIN_PANEL_ENABLED", True)
    sync_plan_defaults_on_startup: bool = _bool("SYNC_PLAN_DEFAULTS_ON_STARTUP", False)
    terms_version: str = os.getenv("TERMS_VERSION", "2026-10")
    public_api_url: str = os.getenv("PUBLIC_API_URL", "http://127.0.0.1:9000").rstrip("/")
    public_app_url: str = os.getenv("PUBLIC_APP_URL", "https://marketai.example.com").rstrip("/")

    mercado_pago_token: str = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "").strip()
    mercado_pago_webhook_url: str = os.getenv("MERCADOPAGO_WEBHOOK_URL", "").strip()
    mercado_pago_webhook_secret: str = os.getenv("MERCADOPAGO_WEBHOOK_SECRET", "").strip()

    stripe_secret_key: str = os.getenv("STRIPE_SECRET_KEY", "").strip()
    stripe_webhook_secret: str = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()

    paypal_client_id: str = os.getenv("PAYPAL_CLIENT_ID", "").strip()
    paypal_client_secret: str = os.getenv("PAYPAL_CLIENT_SECRET", "").strip()
    paypal_webhook_id: str = os.getenv("PAYPAL_WEBHOOK_ID", "").strip()
    paypal_mode: str = os.getenv("PAYPAL_MODE", "sandbox").strip()

    allow_unverified_webhooks: bool = _bool("ALLOW_UNVERIFIED_WEBHOOKS", False)
    trial_days: int = int(os.getenv("TRIAL_DAYS", "7"))
    trial_analyses: int = int(os.getenv("TRIAL_ANALYSES", "10"))

settings = Settings()
