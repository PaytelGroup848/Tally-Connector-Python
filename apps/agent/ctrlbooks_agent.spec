# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

block_cipher = None

project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))

a = Analysis(
    [os.path.join(project_dir, 'apps', 'agent', 'main.py')],
    pathex=[project_dir],
    binaries=[],
    datas=[],
    hiddenimports=[
        'httpx',
        'shared',
        'shared.models',
        'shared.database',
        'shared.fingerprint',
        'apps',
        'apps.agent',
        'apps.agent.agent_service'
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='ctrlbooks_agent',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,  # Console output for background agent logging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ctrlbooks_agent',
)

