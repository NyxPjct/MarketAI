# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
import sys
from pathlib import Path
sys.path.insert(0,str(Path('../cloud').resolve()))

hiddenimports = []
hiddenimports += collect_submodules('webview')
hiddenimports += collect_submodules('uvicorn')
hiddenimports += collect_submodules('app')

block_cipher = None

a = Analysis(
    ['desktop_launcher.py'],
    pathex=['../cloud'],
    binaries=[],
    datas=[
        ('frontend', 'frontend'),
        ('.env.example', '.'),
        ('docs', 'docs'),
        ('../cloud/releases', 'releases'),
    ],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='MarketAI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='marketai.ico',
    version='version_info.txt',
)
