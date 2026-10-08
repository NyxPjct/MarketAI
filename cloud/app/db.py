from __future__ import annotations
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from app.config import settings

database_url = settings.database_url
# Railway exposes PostgreSQL URLs as postgresql://. MarketAI ships Psycopg 3,
# so normalize the SQLAlchemy dialect explicitly instead of depending on psycopg2.
if database_url.startswith("postgresql://"):
    database_url = "postgresql+psycopg://" + database_url[len("postgresql://"):]

kwargs = {"pool_pre_ping": True}
if database_url.startswith("sqlite"):
    kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(database_url, **kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

def get_db():
    db=SessionLocal()
    try:
        yield db
    finally:
        db.close()
