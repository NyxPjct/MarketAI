from __future__ import annotations

import base64
import ctypes
import json
import os
import platform
from ctypes import wintypes
from pathlib import Path
from typing import Any, Dict

SECRET_KEYS = (
    "OPENAI_API_KEY",
    "MERCADOLIVRE_ACCESS_TOKEN",
    "EBAY_CLIENT_ID",
    "EBAY_CLIENT_SECRET",
    "SERPAPI_KEY",
)

DEFAULT_PREFERENCES: Dict[str, Any] = {
    "default_origin_country": "CN",
    "default_destination_country": "BR",
    "default_purchase_currency": "BRL",
    "default_marketplace_fee_percent": 16.0,
    "default_taxes_percent": 6.0,
    "default_ads_percent": 3.0,
    "default_margin_percent": 20.0,
    "first_run_completed": False,
}


def data_dir() -> Path:
    explicit = os.getenv("MARKETAI_DATA_DIR", "").strip()
    if explicit:
        root = Path(explicit)
    elif os.getenv("LOCALAPPDATA"):
        root = Path(os.environ["LOCALAPPDATA"]) / "MarketAI"
    else:
        root = Path.home() / ".marketai"
    root.mkdir(parents=True, exist_ok=True)
    return root


def logs_dir() -> Path:
    p = data_dir() / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def preferences_path() -> Path:
    return data_dir() / "preferences.json"


def secrets_path() -> Path:
    return data_dir() / "secrets.bin"


def _load_json(path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    if not path.exists():
        return dict(fallback)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return dict(fallback)
        out = dict(fallback)
        out.update(payload)
        return out
    except Exception:
        return dict(fallback)


def load_preferences() -> Dict[str, Any]:
    return _load_json(preferences_path(), DEFAULT_PREFERENCES)


def save_preferences(values: Dict[str, Any]) -> Dict[str, Any]:
    current = load_preferences()
    allowed = set(DEFAULT_PREFERENCES)
    for key, value in values.items():
        if key not in allowed:
            continue
        if key.startswith("default_") and key.endswith("_percent"):
            try:
                value = max(0.0, min(80.0, float(value)))
            except Exception:
                continue
        if key in {"default_origin_country", "default_destination_country"}:
            value = str(value).upper()[:2]
        if key == "default_purchase_currency":
            value = str(value).upper()[:4]
        if key == "first_run_completed":
            value = bool(value)
        current[key] = value
    preferences_path().write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


# Minimal Windows DPAPI wrapper: encrypted secrets are bound to the current Windows user.
class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob_from_bytes(data: bytes):
    if not data:
        return DATA_BLOB(0, None), None
    buf = (ctypes.c_byte * len(data)).from_buffer_copy(data)
    return DATA_BLOB(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_byte))), buf




def _windows_crypto():
    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), ctypes.c_wchar_p, ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), ctypes.POINTER(ctypes.c_wchar_p), ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB)
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _dpapi_encrypt(data: bytes) -> bytes:
    if os.name != "nt":
        return b"DEV0" + base64.b64encode(data)
    in_blob, in_buf = _blob_from_bytes(data)
    out_blob = DATA_BLOB()
    crypt32, kernel32 = _windows_crypto()
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        ctypes.c_wchar_p("MarketAI"),
        None,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return b"DP01" + ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))
        _ = in_buf


def _dpapi_decrypt(data: bytes) -> bytes:
    if data.startswith(b"DEV0"):
        return base64.b64decode(data[4:])
    if not data.startswith(b"DP01"):
        raise ValueError("Formato de segredo desconhecido")
    payload = data[4:]
    if os.name != "nt":
        raise ValueError("Segredos DPAPI só podem ser lidos no Windows pelo mesmo usuário")
    in_blob, in_buf = _blob_from_bytes(payload)
    out_blob = DATA_BLOB()
    crypt32, kernel32 = _windows_crypto()
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob), None, None, None, None, CRYPTPROTECT_UI_FORBIDDEN, ctypes.byref(out_blob)
    )
    if not ok:
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))
        _ = in_buf


def load_secrets() -> Dict[str, str]:
    path = secrets_path()
    if not path.exists():
        return {}
    try:
        raw = _dpapi_decrypt(path.read_bytes())
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            return {}
        return {k: str(v) for k, v in payload.items() if k in SECRET_KEYS and v}
    except Exception:
        return {}




def _scrub_legacy_env(keys: list[str]) -> None:
    env_path = os.getenv("MARKETAI_ENV_PATH", "").strip()
    if not env_path:
        return
    path = Path(env_path)
    if not path.exists():
        return
    try:
        target = set(keys)
        lines = path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines:
            raw = line.strip()
            if raw and not raw.startswith("#") and "=" in raw:
                key = raw.split("=", 1)[0].strip()
                if key in target:
                    out.append(f"{key}=")
                    continue
            out.append(line)
        path.write_text("\n".join(out) + "\n", encoding="utf-8")
    except Exception:
        pass

def save_secrets(values: Dict[str, Any], clear: list[str] | None = None) -> Dict[str, bool]:
    current = load_secrets()
    cleared = [key for key in (clear or []) if key in SECRET_KEYS]
    for key in cleared:
        current.pop(key, None)
        os.environ.pop(key, None)
    if cleared:
        _scrub_legacy_env(cleared)
    for key, value in values.items():
        if key not in SECRET_KEYS:
            continue
        text = str(value or "").strip()
        if text:
            current[key] = text
    payload = json.dumps(current, ensure_ascii=False).encode("utf-8")
    secrets_path().write_bytes(_dpapi_encrypt(payload))
    apply_saved_secrets_to_environment()
    return {k: bool(current.get(k)) for k in SECRET_KEYS}


def apply_saved_secrets_to_environment() -> None:
    for key, value in load_secrets().items():
        os.environ[key] = value


def secret_presence() -> Dict[str, bool]:
    encrypted = load_secrets()
    return {key: bool(encrypted.get(key) or os.getenv(key, "").strip()) for key in SECRET_KEYS}


def platform_info() -> Dict[str, str]:
    return {
        "os": platform.platform(),
        "python": platform.python_version(),
        "data_dir": str(data_dir()),
        "secrets_storage": "Windows DPAPI" if os.name == "nt" else "dev fallback",
    }


# --- MarketAI Cloud session (refresh/access tokens protected with the same Windows DPAPI) ---
def cloud_session_path() -> Path:
    return data_dir() / "cloud-session.bin"

def load_cloud_session() -> Dict[str, Any]:
    p=cloud_session_path()
    if not p.exists(): return {}
    try:
        return json.loads(_dpapi_decrypt(p.read_bytes()).decode("utf-8"))
    except Exception:
        return {}

def save_cloud_session(values: Dict[str, Any]) -> Dict[str, Any]:
    p=cloud_session_path(); p.write_bytes(_dpapi_encrypt(json.dumps(values,ensure_ascii=False).encode("utf-8"))); return values

def clear_cloud_session() -> None:
    p=cloud_session_path()
    if p.exists():
        try: p.unlink()
        except Exception: pass
