"""Embedded, loopback-only MarketAI service with a persistent local profile."""
from __future__ import annotations
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time

import httpx
import uvicorn

class LocalRuntime:
    def __init__(self):
        from backend.services.settings import data_dir, _dpapi_encrypt, _dpapi_decrypt, apply_saved_secrets_to_environment
        from dotenv import load_dotenv
        from backend.logging_config import configure_logging
        configure_logging()
        load_dotenv(os.getenv('MARKETAI_ENV_PATH', str(data_dir()/'.env')))
        apply_saved_secrets_to_environment()
        root=data_dir()/'local-service';root.mkdir(parents=True,exist_ok=True)
        key=root/'identity.bin'
        if key.exists():
            jwt=_dpapi_decrypt(key.read_bytes()).decode('ascii')
        else:
            jwt=secrets.token_urlsafe(48);key.write_bytes(_dpapi_encrypt(jwt.encode('ascii')))
            if os.name!='nt':key.chmod(0o600)
        self.socket=socket.socket();self.socket.bind(('127.0.0.1',0))
        self.port=self.socket.getsockname()[1]
        self.url=f'http://127.0.0.1:{self.port}'
        os.environ.update(MARKETAI_LOCAL_MODE='1',MARKETAI_CLOUD_URL=self.url,
            DATABASE_URL='sqlite:///'+(root/'marketai.db').as_posix(),JWT_SECRET=jwt,
            ADMIN_API_KEY='',ADMIN_EMAIL='',ADMIN_PASSWORD='',ADMIN_PANEL_ENABLED='0',
            BATCH_WORKER_ENABLED='1',PUBLIC_API_URL=self.url,PUBLIC_APP_URL=self.url)
        if not getattr(sys,'frozen',False):
            sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'cloud'))
        from app.main import app
        from starlette.middleware.trustedhost import TrustedHostMiddleware
        app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost'])
        original=app.router.lifespan_context
        @asynccontextmanager
        async def lifespan(application):
            async with original(application):
                async def monitor():
                    from app.sentinel_worker import cycle, INTERVAL
                    while True:
                        try:await cycle()
                        except Exception:
                            import logging
                            logging.getLogger('marketai.local').exception('Local monitoring cycle failed')
                        await asyncio.sleep(INTERVAL*60)
                worker=asyncio.create_task(monitor())
                try:yield
                finally:
                    worker.cancel()
                    try:await worker
                    except asyncio.CancelledError:pass
        app.router.lifespan_context=lifespan
        self.server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=self.port,
            log_level='warning',access_log=False,server_header=False,use_colors=False))
        self.thread=threading.Thread(target=lambda:self.server.run(sockets=[self.socket]),daemon=True,name='MarketAI-local')

    def start(self):
        self.thread.start()
        with httpx.Client(trust_env=False,timeout=1) as client:
            deadline=time.monotonic()+30
            while time.monotonic()<deadline:
                try:
                    if client.get(self.url+'/health').is_success:break
                except httpx.HTTPError:pass
                if not self.thread.is_alive():raise RuntimeError('Local service could not start')
                time.sleep(.1)
            else:raise RuntimeError('Local service startup timed out')
        self.authorize()
        return self

    def authorize(self):
        from app.db import SessionLocal
        from app.models import User, Subscription, Device, RefreshSession
        from app.main import issue_tokens
        from app.security import hash_password
        from backend.services.cloud import device_uuid
        from backend.services.settings import save_cloud_session
        device=device_uuid()
        with SessionLocal() as db:
            user=db.query(User).filter_by(email='local@marketai.local').first()
            if user is None:
                user=User(email='local@marketai.local',full_name='Local profile',
                    password_hash=hash_password(secrets.token_urlsafe(40)),status='active')
                db.add(user);db.flush()
                db.add(Subscription(user_id=user.id,plan_code='community',status='active',provider='open_source'))
            if not db.query(Device).filter_by(user_id=user.id,device_uuid=device,active=True).first():
                db.add(Device(user_id=user.id,device_uuid=device,name='Local computer',active=True))
            db.query(RefreshSession).filter_by(user_id=user.id,device_uuid=device).update({'revoked':True})
            tokens=issue_tokens(db,user,device)
            save_cloud_session({'access_token':tokens['access_token'],'refresh_token':tokens['refresh_token'],
                'account':tokens['user'],'entitlement':tokens['entitlement']})

    def stop(self):
        self.server.should_exit=True
        self.thread.join(timeout=15)
        self.socket.close()


def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--data-dir',required=True)
    parser.add_argument('--desktop-port',type=int,default=8000)
    args=parser.parse_args()
    os.environ['MARKETAI_DATA_DIR']=args.data_dir
    service=LocalRuntime()
    try:
        service.start()
        from backend.main import app
        uvicorn.run(app,host='127.0.0.1',port=args.desktop_port)
    finally:service.stop()

if __name__=='__main__':main()
