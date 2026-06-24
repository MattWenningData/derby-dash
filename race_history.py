from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any


# ── File path ──────────────────────────────────────────────────────────────────

def get_history_path() -> Path:
    """Return path to race_history.csv in the user's writable data folder."""
    from paths import race_history_path
    return race_history_path()


# ── CSV schema ─────────────────────────────────────────────────────────────────

_FIELDNAMES = [
    'date',
    'time',
    'winner',
    'total_rolls',
    'winning_combinations',
    'approximate_odds',
    'roll_sequence',          # "3+4=7; 1+6=7; ..."
    'final_positions',        # "2:1, 3:2, 4:0, ..."
]


# ── Save a completed race ──────────────────────────────────────────────────────

def save_race(game_state) -> Path:
    """
    Append one row to race_history.csv for the just-completed race.
    Returns the path to the CSV file.
    """
    from constants import COMBINATIONS, HORSE_NUMBERS

    path = get_history_path()
    write_header = not path.exists() or path.stat().st_size == 0

    now = datetime.now()
    winner  = game_state.winner
    combos  = COMBINATIONS.get(winner, 0) if winner else 0
    odds    = (36 // combos) if combos else 0

    roll_seq = '; '.join(
        f'{d1}+{d2}={d1+d2}' for d1, d2 in game_state.roll_log
    )
    final_pos = ', '.join(
        f'{n}:{game_state.positions.get(n, 0)}' for n in HORSE_NUMBERS
    )

    row: Dict[str, Any] = {
        'date':                 now.strftime('%Y-%m-%d'),
        'time':                 now.strftime('%H:%M:%S'),
        'winner':               winner if winner else '',
        'total_rolls':          len(game_state.roll_log),
        'winning_combinations': combos,
        'approximate_odds':     f'{odds}:1' if odds else '',
        'roll_sequence':        roll_seq,
        'final_positions':      final_pos,
    }

    with open(path, 'a', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES)
        if write_header:
            writer.writeheader()
        writer.writerow(row)

    return path


# ── Load history for the viewer ────────────────────────────────────────────────

def load_history() -> List[Dict[str, str]]:
    """Return all saved races as a list of dicts (newest first)."""
    path = get_history_path()
    if not path.exists():
        return []
    with open(path, newline='', encoding='utf-8') as fh:
        rows = list(csv.DictReader(fh))
    return list(reversed(rows))
