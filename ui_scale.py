"""
Global UI scale factor for Truck Dash.

Set once at startup (main.py) based on screen DPI and physical size.
All widgets read it via get_scale() to produce TV-friendly sizing.
"""
from __future__ import annotations

_scale: float = 1.0


def set_scale(value: float) -> None:
    global _scale
    _scale = max(0.8, min(3.5, float(value)))


def get_scale() -> float:
    return _scale
