# -*- mode: python ; coding: utf-8 -*-

import os
import sys
from PyInstaller.building.build_main import Analysis, PYZ, EXE, COLLECT

block_cipher = None

if 'SPEC' in globals():
    spec_dir = os.path.dirname(os.path.abspath(SPEC))
else:
    spec_dir = os.path.abspath(os.path.join('apps', 'desktop_app'))

project_dir = os.path.abspath(os.path.join(spec_dir, '..', '..'))
assets_dir = os.path.join(project_dir, 'apps', 'desktop_app', 'assets')

datas = []
if os.path.exists(assets_dir):
    datas.append((assets_dir, os.path.join('apps', 'desktop_app', 'assets')))

env_file = os.path.join(project_dir, '.env')
if os.path.exists(env_file):
    datas.append((env_file, '.'))

icon_file = os.path.join(assets_dir, 'app_icon.ico')
if not os.path.exists(icon_file):
    icon_file = os.path.join(assets_dir, 'app_icon.png')

a = Analysis(
    [os.path.join(project_dir, 'apps', 'desktop_app', 'main.py')],
    pathex=[project_dir],
    binaries=[],
    datas=datas,
    hiddenimports=[
        'sqlite3',
        'sqlalchemy',
        'sqlalchemy.dialects.sqlite',
        'sqlalchemy.sql.default_comparator',
        'alembic',
        'requests',
        'httpx',
        'cryptography',
        'certifi',
        'pymongo',
        'pymongo.srv',
        'bson',
        'dns',
        'dns.resolver',
        'pydantic',
        'pydantic_core',
        'PySide6',
        'PySide6.QtCore',
        'PySide6.QtGui',
        'PySide6.QtWidgets',
        'shared',
        'shared.config',
        'shared.constants',
        'shared.auth',
        'shared.auth.cloud_auth_service',
        'shared.db',
        'shared.db.mongo_client',
        'shared.db.models',
        'shared.db.models.connector',
        'shared.db.models.storage',
        'shared.db.models.extraction',
        'shared.db.models.metadata',
        'shared.db.models.mapping',
        'shared.db.models.user',
        'shared.db.models.system',
        'shared.models',
        'shared.database',
        'shared.fingerprint',
        'shared.extraction',
        'shared.extraction.base',
        'shared.extraction.tally_extractor',
        'shared.repositories',
        'shared.repositories.base',
        'shared.repositories.connector_repo',
        'shared.repositories.company_repository',
        'shared.repositories.extraction_repo',
        'shared.repositories.metadata_repo',
        'shared.repositories.storage_repo',
        'shared.repositories.mapping_repo',
        'shared.repositories.user_repo',
        'shared.repositories.system_repo',
        'shared.logging_config',
        'apps',
        'apps.desktop_app',
        'apps.desktop_app.main',
        'apps.desktop_app.ui',
        'apps.desktop_app.ui.main_window',
        'apps.desktop_app.ui.tray_icon',
        'apps.desktop_app.ui.widgets',
        'apps.desktop_app.ui.widgets.lk_header',
        'apps.desktop_app.ui.widgets.lk_footer',
        'apps.desktop_app.ui.screens',
        'apps.desktop_app.ui.screens.login_screen',
        'apps.desktop_app.ui.screens.connection_probe_screen',
        'apps.desktop_app.ui.screens.connected_dashboard_screen',
        'apps.desktop_app.ui.screens.profile_screen',
        'apps.desktop_app.ui.screens.connection_settings_screen',
        'apps.desktop_app.ui.screens.system_requirement_screen',
        'apps.desktop_app.ui.screens.activity_history_screen',
        'shared.updater',
        'apps.desktop_app.ui.widgets.update_dialog',
        'apps.desktop_app.ui.threads',
        'apps.desktop_app.ui.threads.sync_worker',
        'apps.desktop_app.ui.threads.command_worker',
        'apps.desktop_app.ui.threads.company_fetch_worker',
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
    name='ctrlbooks',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  
    icon=icon_file if os.path.exists(icon_file) else None,
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
    name='ctrlbooks',
)

