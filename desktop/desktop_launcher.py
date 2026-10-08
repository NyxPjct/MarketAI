from __future__ import annotations

import ctypes
from ctypes import wintypes
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

import uvicorn
import webview

APP_NAME = "MarketAI"
APP_VERSION = "1.0.2"
MUTEX_NAME = "Local\\MarketAI.Desktop.v1.0"


def install_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def bundled_directory() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return Path(__file__).resolve().parent


def user_data_directory() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) / APP_NAME if base else Path.home() / ".marketai"
    root.mkdir(parents=True, exist_ok=True)
    return root


def show_message(title: str, message: str, error: bool = False) -> None:
    if os.name == "nt":
        flags = 0x10 if error else 0x40
        ctypes.windll.user32.MessageBoxW(None, message, title, flags)
    else:
        print(f"{title}: {message}", file=sys.stderr if error else sys.stdout)


def _kernel32():
    k32 = ctypes.windll.kernel32
    k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, ctypes.c_wchar_p]
    k32.CreateMutexW.restype = wintypes.HANDLE
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    k32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    k32.ReleaseMutex.restype = wintypes.BOOL
    return k32


def acquire_single_instance():
    if os.name != "nt":
        return None
    k32 = _kernel32()
    handle = k32.CreateMutexW(None, False, MUTEX_NAME)
    already_exists = k32.GetLastError() == 183
    if already_exists:
        if handle:
            k32.CloseHandle(handle)
        return False
    return handle


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_until_ready(port: int, timeout: float = 15.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.08)
    return False


def configure_paths() -> None:
    data_root = user_data_directory()
    os.environ["MARKETAI_DATA_DIR"] = str(data_root)

    # Compatibilidade: um .env legado ainda pode ser importado, mas a edição Community
    # grava novas credenciais criptografadas pelo Windows DPAPI.
    legacy_env = data_root / ".env"
    portable_env = install_directory() / ".env"
    env_file = portable_env if portable_env.exists() else legacy_env
    os.environ["MARKETAI_ENV_PATH"] = str(env_file)

    example_target = data_root / ".env.example"
    if not example_target.exists():
        for candidate in (install_directory() / ".env.example", bundled_directory() / ".env.example"):
            if candidate.exists():
                try:
                    example_target.write_bytes(candidate.read_bytes())
                except OSError:
                    pass
                break


def write_startup_error(exc: BaseException) -> Path:
    path = user_data_directory() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    file = path / "startup-error.log"
    file.write_text(
        f"MarketAI v{APP_VERSION}\n\n{type(exc).__name__}: {exc}\n\n{traceback.format_exc()}",
        encoding="utf-8",
    )
    return file


def main() -> int:
    mutex = acquire_single_instance()
    if mutex is False:
        show_message(APP_NAME, "O MarketAI já está aberto.")
        return 0

    server = None
    thread = None
    try:
        configure_paths()
        from backend.main import app

        port = choose_port()
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
            server_header=False,
        )
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, name="MarketAI-API", daemon=True)
        thread.start()

        if not wait_until_ready(port):
            raise RuntimeError("O serviço interno do MarketAI não iniciou dentro do tempo esperado.")

        storage_dir = user_data_directory() / "webview"
        storage_dir.mkdir(parents=True, exist_ok=True)

        webview.create_window(
            f"MarketAI v{APP_VERSION} — Inteligência Comercial · Community",
            f"http://127.0.0.1:{port}",
            width=1440,
            height=900,
            min_size=(1080, 700),
            resizable=True,
            text_select=True,
        )
        webview.start(debug=False, private_mode=False, storage_path=str(storage_dir))
        return 0
    except Exception as exc:
        log_path = write_startup_error(exc)
        show_message(
            "MarketAI — erro de inicialização",
            f"Não foi possível iniciar o MarketAI.\n\nUm relatório foi salvo em:\n{log_path}",
            error=True,
        )
        return 2
    finally:
        if server is not None:
            server.should_exit = True
        if thread is not None:
            thread.join(timeout=2.5)
        if os.name == "nt" and mutex not in (None, False):
            k32 = _kernel32()
            k32.ReleaseMutex(mutex)
            k32.CloseHandle(mutex)


if __name__ == "__main__":
    raise SystemExit(main())
