from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, UniqueConstraint, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

def utcnow(): return datetime.now(timezone.utc)
def uid(): return str(uuid.uuid4())

class User(Base):
    __tablename__="users"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    email: Mapped[str]=mapped_column(String(320),unique=True,index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    full_name: Mapped[str]=mapped_column(String(160),default="")
    role: Mapped[str]=mapped_column(String(20),default="user")
    status: Mapped[str]=mapped_column(String(20),default="active")
    email_verified: Mapped[bool]=mapped_column(Boolean,default=False)
    terms_version: Mapped[str]=mapped_column(String(40),default="")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    deleted_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    subscription=relationship("Subscription",back_populates="user",uselist=False,cascade="all, delete-orphan")

class Plan(Base):
    __tablename__="plans"
    code: Mapped[str]=mapped_column(String(32),primary_key=True)
    name: Mapped[str]=mapped_column(String(80))
    price_brl: Mapped[float]=mapped_column(Float)
    analyses_per_month: Mapped[int]=mapped_column(Integer)
    device_limit: Mapped[int]=mapped_column(Integer)
    active: Mapped[bool]=mapped_column(Boolean,default=True)

class Subscription(Base):
    __tablename__="subscriptions"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),unique=True,index=True)
    plan_code: Mapped[str]=mapped_column(ForeignKey("plans.code"),default="essencial")
    status: Mapped[str]=mapped_column(String(24),default="trialing")
    provider: Mapped[str]=mapped_column(String(32),default="trial")
    provider_subscription_id: Mapped[str|None]=mapped_column(String(120),nullable=True,index=True)
    trial_end: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    current_period_end: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)
    user=relationship("User",back_populates="subscription")
    plan=relationship("Plan")

class RefreshSession(Base):
    __tablename__="refresh_sessions"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
    token_hash: Mapped[str]=mapped_column(String(64),unique=True,index=True)
    device_uuid: Mapped[str]=mapped_column(String(80),default="")
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool]=mapped_column(Boolean,default=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class Device(Base):
    __tablename__="devices"
    __table_args__=(UniqueConstraint("user_id","device_uuid",name="uq_user_device"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
    device_uuid: Mapped[str]=mapped_column(String(80),index=True)
    name: Mapped[str]=mapped_column(String(160),default="Windows PC")
    active: Mapped[bool]=mapped_column(Boolean,default=True)
    first_seen: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    last_seen: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class UsageCounter(Base):
    __tablename__="usage_counters"
    __table_args__=(UniqueConstraint("user_id","period_key",name="uq_usage_period"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
    period_key: Mapped[str]=mapped_column(String(12),index=True)
    analyses_used: Mapped[int]=mapped_column(Integer,default=0)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)

class License(Base):
    __tablename__="licenses"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    code_hash: Mapped[str]=mapped_column(String(64),unique=True,index=True)
    code_hint: Mapped[str]=mapped_column(String(16),default="")
    plan_code: Mapped[str]=mapped_column(ForeignKey("plans.code"))
    duration_days: Mapped[int]=mapped_column(Integer,default=30)
    max_redemptions: Mapped[int]=mapped_column(Integer,default=1)
    redeemed_count: Mapped[int]=mapped_column(Integer,default=0)
    active: Mapped[bool]=mapped_column(Boolean,default=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class LicenseRedemption(Base):
    __tablename__="license_redemptions"
    __table_args__=(UniqueConstraint("license_id","user_id",name="uq_license_user"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    license_id: Mapped[str]=mapped_column(ForeignKey("licenses.id"),index=True)
    user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
    redeemed_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class AuditEvent(Base):
    __tablename__="audit_events"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    user_id: Mapped[str|None]=mapped_column(String(36),nullable=True,index=True)
    event: Mapped[str]=mapped_column(String(80),index=True)
    detail: Mapped[str]=mapped_column(Text,default="")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class BillingTransaction(Base):
    __tablename__="billing_transactions"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
    plan_code: Mapped[str]=mapped_column(ForeignKey("plans.code"),index=True)
    provider: Mapped[str]=mapped_column(String(32),index=True)
    payment_method: Mapped[str]=mapped_column(String(32),index=True)
    provider_object_id: Mapped[str|None]=mapped_column(String(160),nullable=True,index=True)
    status: Mapped[str]=mapped_column(String(32),default="pending",index=True)
    amount: Mapped[float]=mapped_column(Float,default=0)
    currency: Mapped[str]=mapped_column(String(8),default="BRL")
    period_days: Mapped[int]=mapped_column(Integer,default=30)
    checkout_url: Mapped[str]=mapped_column(Text,default="")
    credited_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)

class ProviderPlan(Base):
    __tablename__="provider_plans"
    __table_args__=(UniqueConstraint("provider","app_plan_code","currency",name="uq_provider_app_plan_currency"),)
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    provider: Mapped[str]=mapped_column(String(32),index=True)
    app_plan_code: Mapped[str]=mapped_column(ForeignKey("plans.code"),index=True)
    currency: Mapped[str]=mapped_column(String(8),default="USD")
    provider_product_id: Mapped[str|None]=mapped_column(String(160),nullable=True)
    provider_plan_id: Mapped[str]=mapped_column(String(160),index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)

class ProductWatch(Base):
    __tablename__="product_watches"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
    product_name: Mapped[str]=mapped_column(String(240),index=True)
    variant_text: Mapped[str]=mapped_column(String(240),default="")
    country: Mapped[str]=mapped_column(String(8),default="BR",index=True)
    settings_json: Mapped[str]=mapped_column(Text,default="{}")
    active: Mapped[bool]=mapped_column(Boolean,default=True,index=True)
    autopilot_enabled: Mapped[bool]=mapped_column(Boolean,default=False)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow)
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,onupdate=utcnow)

class MarketSnapshot(Base):
    __tablename__="market_snapshots"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    watch_id: Mapped[str]=mapped_column(ForeignKey("product_watches.id"),index=True)
    user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
    market_median: Mapped[float|None]=mapped_column(Float,nullable=True)
    market_min: Mapped[float|None]=mapped_column(Float,nullable=True)
    market_max: Mapped[float|None]=mapped_column(Float,nullable=True)
    listing_count: Mapped[int]=mapped_column(Integer,default=0)
    quality_score: Mapped[float]=mapped_column(Float,default=0)
    market_score: Mapped[float|None]=mapped_column(Float,nullable=True)
    net_margin: Mapped[float|None]=mapped_column(Float,nullable=True)
    suggested_price: Mapped[float|None]=mapped_column(Float,nullable=True)
    payload_json: Mapped[str]=mapped_column(Text,default="{}")
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,index=True)

class IntelligenceAlert(Base):
    __tablename__="intelligence_alerts"
    id: Mapped[str]=mapped_column(String(36),primary_key=True,default=uid)
    user_id: Mapped[str]=mapped_column(ForeignKey("users.id"),index=True)
    watch_id: Mapped[str|None]=mapped_column(ForeignKey("product_watches.id"),nullable=True,index=True)
    severity: Mapped[str]=mapped_column(String(24),default="info",index=True)
    kind: Mapped[str]=mapped_column(String(48),default="market",index=True)
    title: Mapped[str]=mapped_column(String(220))
    message: Mapped[str]=mapped_column(Text,default="")
    acknowledged: Mapped[bool]=mapped_column(Boolean,default=False,index=True)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utcnow,index=True)
