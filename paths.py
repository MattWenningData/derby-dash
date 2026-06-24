"""
Centralised path resolution for Truck Dash.

When running as a frozen PyInstaller bundle the app is installed in
Program Files (read-only).  All user-writable data goes to:
    %APPDATA%/TruckDash/

During development every path resolves to the source directory so
nothing changes from the current workflow.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def _user_data_dir() -> Path:
    if getattr(sys, 'frozen', False):
        base = Path(os.environ.get('APPDATA', Path.home())) / 'TruckDash'
    else:
        base = Path(__file__).parent
    base.mkdir(parents=True, exist_ok=True)
    return base


def race_history_path() -> Path:
    return _user_data_dir() / 'race_history.csv'


def webcam_config_path() -> Path:
    return _user_data_dir() / 'webcam_config.json'


def training_data_dir() -> Path:
    d = _user_data_dir() / 'training_data'
    d.mkdir(parents=True, exist_ok=True)
    return d
