# -*- mode: python ; coding: utf-8 -*-
# TruckDash.spec  —  PyInstaller build spec
#
# Build with:  py -3 -m PyInstaller TruckDash.spec

import os
from pathlib import Path

block_cipher = None

# Collect training_data if it exists (pre-seeded reference frames)
_here = Path(SPECPATH)
_extra_datas = []
if (_here / 'training_data').exists():
    _extra_datas.append(('training_data', 'training_data'))

a = Analysis(
    ['main.py'],
    pathex=[str(_here)],
    binaries=[],
    datas=_extra_datas,
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.QtSvg',
        'cv2',
        'numpy',
        'paths',
        'constants',
        'game_state',
        'styles',
        'board_widget',
        'control_panel',
        'main_window',
        'admin_dialog',
        'webcam_dialog',
        'history_dialog',
        'race_history',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy', 'pandas'],
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
    name='TruckDash',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX can trigger antivirus; leave off
    console=False,      # No console window for end users
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='TruckDash.ico' if os.path.exists('TruckDash.ico') else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='TruckDash',
)
