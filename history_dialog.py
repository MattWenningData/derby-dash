from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout,
)

from race_history import get_history_path, load_history


class HistoryDialog(QDialog):
    """Browse past race results stored in race_history.csv."""

    _COLUMNS = [
        ('Date',       'date',                  90),
        ('Time',       'time',                  70),
        ('Winner',     'winner',                60),
        ('Rolls',      'total_rolls',           55),
        ('Combos',     'winning_combinations',  60),
        ('Odds',       'approximate_odds',      60),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle('📋  Race History')
        self.setMinimumSize(620, 420)
        self._build()
        self._load()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(14, 14, 14, 14)

        # Title
        title = QLabel('Race History')
        title.setObjectName('title')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        # Path info
        self.path_lbl = QLabel('')
        self.path_lbl.setStyleSheet('color: #888; font-size: 10px;')
        self.path_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.path_lbl)

        # Table
        self.table = QTableWidget(0, len(self._COLUMNS))
        self.table.setHorizontalHeaderLabels([c[0] for c in self._COLUMNS])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        for col_idx, (_, _, width) in enumerate(self._COLUMNS):
            self.table.setColumnWidth(col_idx, width)
        root.addWidget(self.table, stretch=1)

        # Roll sequence label
        self.detail_lbl = QLabel('Select a row to see the full roll sequence.')
        self.detail_lbl.setWordWrap(True)
        self.detail_lbl.setStyleSheet('color: #C8A84B; font-size: 11px; padding: 4px;')
        root.addWidget(self.detail_lbl)
        self.table.itemSelectionChanged.connect(self._on_select)

        # Buttons
        btn_row = QHBoxLayout()

        btn_open = QPushButton('📂  Open CSV File')
        btn_open.clicked.connect(self._open_csv)

        btn_refresh = QPushButton('🔄  Refresh')
        btn_refresh.clicked.connect(self._load)

        btn_close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btn_close.rejected.connect(self.accept)

        btn_row.addWidget(btn_open)
        btn_row.addWidget(btn_refresh)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        root.addLayout(btn_row)

    def _load(self):
        path = get_history_path()
        self.path_lbl.setText(f'CSV: {path}')

        rows = load_history()
        self._rows_data = rows

        self.table.setRowCount(len(rows))
        for row_idx, race in enumerate(rows):
            winner_n = race.get('winner', '')
            for col_idx, (_, key, _) in enumerate(self._COLUMNS):
                text = race.get(key, '')
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                if key == 'winner' and winner_n:
                    from constants import HORSE_COLORS
                    color = HORSE_COLORS.get(int(winner_n), '#F0E8D0')
                    item.setForeground(QColor(color))
                    font = QFont()
                    font.setBold(True)
                    item.setFont(font)
                self.table.setItem(row_idx, col_idx, item)

        if not rows:
            self.detail_lbl.setText('No races recorded yet.')

    def _on_select(self):
        selected = self.table.selectedItems()
        if not selected:
            return
        row_idx = self.table.currentRow()
        if row_idx < 0 or row_idx >= len(self._rows_data):
            return
        race = self._rows_data[row_idx]
        seq  = race.get('roll_sequence', '')
        pos  = race.get('final_positions', '')
        winner = race.get('winner', '?')
        rolls  = race.get('total_rolls', '?')
        self.detail_lbl.setText(
            f'<b>Horse #{winner}</b> won in <b>{rolls}</b> rolls.  '
            f'<span style="color:#888">Rolls: {seq}</span>'
        )

    def _open_csv(self):
        path = get_history_path()
        if not path.exists():
            QMessageBox.information(self, 'No History', 'No races have been recorded yet.')
            return
        if sys.platform == 'win32':
            subprocess.Popen(['explorer', str(path)])
        else:
            subprocess.Popen(['xdg-open', str(path)])
