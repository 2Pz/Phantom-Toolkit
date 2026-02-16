# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all
from pathlib import Path

block_cipher = None

datas = [('..\\gui\\dist', 'gui_dist'), ('..\\phantom_backend\\games', 'phantom_backend\\games')]
binaries = []
hiddenimports = ['uvicorn', 'fastapi', 'engineio.async_drivers.asyncio']
tmp_ret = collect_all('phantom_backend')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]

a = Analysis(
    ['..\\phantom_backend\\main_desktop.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['PySide6', 'qtpy', 'tkinter', 'unittest', 'pydoc'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='PhantomToolkit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    uac_admin=False,
    icon=['..\\build\\assets\\phantom-toolkit.ico'],
    # Use SPECPATH (PyInstaller-provided) since __file__ is not defined here.
    version=str(Path(SPECPATH) / "version_file.txt"),
)
