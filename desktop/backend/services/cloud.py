from __future__ import annotations
import asyncio, json, os, socket, uuid, platform, subprocess, tempfile, hashlib
from pathlib import Path
import httpx
from backend.services.settings import data_dir, load_cloud_session, save_cloud_session, clear_cloud_session

from backend.cloud_build import CLOUD_URL as BUILD_CLOUD_URL
DEFAULT_CLOUD_URL=os.getenv("MARKETAI_CLOUD_URL",BUILD_CLOUD_URL).rstrip("/")
PUBLIC_UPDATE_MANIFEST='https://raw.githubusercontent.com/NyxPjct/MarketAI/main/cloud/releases/windows-stable.json'

async def latest_update():
    if os.getenv('MARKETAI_LOCAL_MODE')=='1':
        # Public metadata uses the normal external network configuration, without
        # account tokens. Local mode must not depend on a hosted API for updates.
        async with httpx.AsyncClient(timeout=10,follow_redirects=True) as client:
            response=await client.get(PUBLIC_UPDATE_MANIFEST)
    else:
        response=await request('GET','/v1/updates/latest',auth=False)
    return response

def device_uuid():
    p=data_dir()/"device.id"
    if p.exists(): return p.read_text(encoding="utf-8").strip()
    value=str(uuid.uuid4()); p.write_text(value,encoding="utf-8"); return value

def device_name(): return f"{platform.node() or 'Windows PC'} · {platform.system()}"

_refresh_lock = asyncio.Lock()
_session_epoch = 0

async def _refresh(base=DEFAULT_CLOUD_URL, rejected_access=None):
    async with _refresh_lock:
        sess=load_cloud_session(); ref=sess.get("refresh_token"); epoch=_session_epoch
        if rejected_access is not None and sess.get("access_token") != rejected_access:
            return sess.get("access_token")
        if not ref: return None
        async with httpx.AsyncClient(timeout=20,trust_env=os.getenv("MARKETAI_LOCAL_MODE")!="1") as c:
            r=await c.post(base+"/v1/auth/refresh",json={"refresh_token":ref})
        if epoch != _session_epoch or load_cloud_session().get("refresh_token") != ref:
            return None
        if r.status_code in {401,403}:
            clear_cloud_session(); return None
        r.raise_for_status()
        d=r.json()
        save_cloud_session({"refresh_token":d["refresh_token"],"access_token":d["access_token"],"account":d.get("user"),"entitlement":d.get("entitlement")})
        return d["access_token"]

async def request(method,path,*,json_data=None,data=None,files=None,auth=True,base=DEFAULT_CLOUD_URL):
    sess=load_cloud_session(); token=sess.get("access_token"); headers={}
    if auth and token:
        headers["Authorization"]="Bearer "+token
        headers["X-Device-Id"]=device_uuid()
    async with httpx.AsyncClient(timeout=45,trust_env=os.getenv("MARKETAI_LOCAL_MODE")!="1") as c:r=await c.request(method,base+path,headers=headers,json=json_data,data=data,files=files)
    if auth and r.status_code==401:
        token=await _refresh(base, rejected_access=token)
        if token:
            headers["Authorization"]="Bearer "+token
            async with httpx.AsyncClient(timeout=45,trust_env=os.getenv("MARKETAI_LOCAL_MODE")!="1") as c:r=await c.request(method,base+path,headers=headers,json=json_data,data=data,files=files)
    return r

async def login(email,password):
    global _session_epoch
    _session_epoch += 1
    epoch = _session_epoch
    async with httpx.AsyncClient(timeout=20,trust_env=os.getenv("MARKETAI_LOCAL_MODE")!="1") as c:r=await c.post(DEFAULT_CLOUD_URL+"/v1/auth/login",json={"email":email,"password":password,"device_uuid":device_uuid()})
    if r.status_code!=200:return r
    if epoch != _session_epoch: raise ValueError("authentication_changed")
    d=r.json(); save_cloud_session({"refresh_token":d["refresh_token"],"access_token":d["access_token"],"account":d.get("user"),"entitlement":d.get("entitlement")});
    await request("POST","/v1/devices/activate",json_data={"device_uuid":device_uuid(),"name":device_name()})
    return r

async def register(email,password,full_name):
    global _session_epoch
    _session_epoch += 1
    epoch = _session_epoch
    async with httpx.AsyncClient(timeout=20,trust_env=os.getenv("MARKETAI_LOCAL_MODE")!="1") as c:r=await c.post(DEFAULT_CLOUD_URL+"/v1/auth/register",json={"email":email,"password":password,"full_name":full_name,"accept_terms":True,"device_uuid":device_uuid()})
    if r.status_code!=200:return r
    if epoch != _session_epoch: raise ValueError("authentication_changed")
    d=r.json(); save_cloud_session({"refresh_token":d["refresh_token"],"access_token":d["access_token"],"account":d.get("user"),"entitlement":d.get("entitlement")}); await request("POST","/v1/devices/activate",json_data={"device_uuid":device_uuid(),"name":device_name()}); return r

async def account_status():
    epoch=_session_epoch
    sess=load_cloud_session()
    if not sess.get("refresh_token") and not sess.get("access_token"):
        return {"authenticated":False,"cloud_url":DEFAULT_CLOUD_URL}
    try:
        r=await request("GET","/v1/account/me")
        if epoch != _session_epoch:
            return {"authenticated":False,"cloud_url":DEFAULT_CLOUD_URL}
        if r.status_code in {401,403}:
            return {"authenticated":False,"cloud_url":DEFAULT_CLOUD_URL,"error":"authentication_required"}
        r.raise_for_status()
        d=r.json()
        current=load_cloud_session()
        if not current.get("access_token"):
            return {"authenticated":False,"cloud_url":DEFAULT_CLOUD_URL}
        save_cloud_session({**current,"account":d.get("user"),"entitlement":d.get("entitlement")})
        return {"authenticated":True,"cloud_url":DEFAULT_CLOUD_URL,"mode":"local" if os.getenv('MARKETAI_LOCAL_MODE')=='1' else "cloud",**d}
    except (httpx.HTTPError,ValueError):
        return {"authenticated":False,"temporary_unavailable":True,"cloud_url":DEFAULT_CLOUD_URL,"error":"cloud_unavailable"}

async def logout():
    global _session_epoch
    _session_epoch += 1
    sess=load_cloud_session(); ref=sess.get("refresh_token")
    clear_cloud_session()
    if ref:
        try: await request("POST","/v1/auth/logout",json_data={"refresh_token":ref},auth=False)
        except httpx.HTTPError: pass


def _version_tuple(value:str):
    out=[]
    for part in str(value).lstrip("vV").split("."):
        try: out.append(int(part))
        except: out.append(0)
    return tuple((out+[0,0,0,0])[:4])

async def download_update(manifest:dict):
    url=str(manifest.get("download_url") or "").strip(); expected=str(manifest.get("sha256") or "").lower().strip()
    if not url or not expected: raise ValueError("update_manifest_incomplete")
    if not (url.startswith("https://") or url.startswith("http://127.0.0.1") or url.startswith("http://localhost")): raise ValueError("update_url_must_be_https")
    target_dir=data_dir()/"updates";target_dir.mkdir(parents=True,exist_ok=True);target=target_dir/f"MarketAI-Setup-{manifest.get('version','update')}.exe"
    async with httpx.AsyncClient(timeout=120,follow_redirects=True) as c:
        async with c.stream("GET",url) as r:
            r.raise_for_status();h=hashlib.sha256()
            with target.open("wb") as f:
                async for chunk in r.aiter_bytes(): h.update(chunk);f.write(chunk)
    if h.hexdigest().lower()!=expected:
        try: target.unlink()
        except: pass
        raise ValueError("update_sha256_mismatch")
    return target

def launch_installer(path:Path):
    if os.name!="nt": return False
    subprocess.Popen([str(path),"/SILENT","/CLOSEAPPLICATIONS","/RESTARTAPPLICATIONS"],close_fds=True)
    return True
