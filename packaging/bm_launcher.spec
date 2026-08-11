# -*- mode: python ; coding: utf-8 -*-
# Ejecutar desde la raíz del repo:
#   py -m PyInstaller packaging/bm_launcher.spec --noconfirm --clean
# Artefacto: dist/BM-Launcher/BM-Launcher.exe (onedir; no commitear)

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

# SPECPATH = directorio que contiene este .spec (PyInstaller)
_packaging = Path(SPECPATH).resolve()
if not (_packaging / 'entry_launcher.py').is_file():
    _packaging = Path(SPECPATH).resolve() / 'packaging'
ROOT = _packaging.parent
os.chdir(ROOT)

block_cipher = None

a = Analysis(
    [str(_packaging / 'entry_launcher.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / 'data' / 'demo' / 'datos_hotel.json'), 'data/demo'),
    ],
    hiddenimports=[
        'flet',
        'flet_desktop',
        'app',
        'app.bootstrap',
        'app.presentation.flet.main',
        'app.presentation.flet.main_inventario',
        'app.presentation.flet.main_administracion',
        'app.presentation.flet.main_launcher',
        'app.core.deploy.runtime',
        'app.core.deploy.config',
    ] + collect_submodules('app'),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[str(_packaging / 'runtime_hook_bm.py')],
    excludes=['matplotlib', 'tkinter', 'test', 'tests'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='BM-Launcher',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='BM-Launcher',
)
