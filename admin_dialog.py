from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QFrame, QGroupBox, QHBoxLayout,
    QLabel, QScrollArea, QSlider, QSpinBox, QVBoxLayout, QWidget,
)

from constants import HORSE_COLORS, HORSE_NUMBERS, TRACK_LENGTHS


class AdminDialog(QDialog):
    """Admin screen — manually adjust any horse's peg position."""

    positions_changed = pyqtSignal()

    def __init__(self, game_state, parent=None):
        super().__init__(parent)
        self.game_state = game_state
        self.setWindowTitle('Admin — Adjust Horse Positions')
        self.setMinimumWidth(520)
        self._rows: dict[int, tuple[QSlider, QSpinBox]] = {}
        self._init_ui()

    # ── UI ─────────────────────────────────────────────────────────────────

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)
        root.setContentsMargins(16, 16, 16, 16)

        title = QLabel('🛠  Horse Position Control')
        title.setObjectName('title')
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)

        note = QLabel(
            'Move any horse to any peg position. '
            'Setting a horse to its maximum position ends the race.'
        )
        note.setWordWrap(True)
        note.setStyleSheet('color: #888; font-size: 11px;')
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(note)

        # ── Scrollable horse rows ──────────────────────────────────────────
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setSpacing(6)

        for horse in HORSE_NUMBERS:
            row = self._make_horse_row(horse)
            scroll_layout.addWidget(row)

        scroll_area.setWidget(scroll_content)
        root.addWidget(scroll_area)

        # ── Buttons ────────────────────────────────────────────────────────
        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        btns.rejected.connect(self.accept)

        reset_btn = btns.addButton('Reset All', QDialogButtonBox.ButtonRole.ResetRole)
        reset_btn.clicked.connect(self._reset_all)

        root.addWidget(btns)

    def _make_horse_row(self, horse: int) -> QGroupBox:
        color  = HORSE_COLORS[horse]
        max_pos = TRACK_LENGTHS[horse]
        cur_pos = self.game_state.positions.get(horse, 0)

        group = QGroupBox()
        group.setStyleSheet(
            f'QGroupBox {{ border: 1px solid {color}40; border-radius: 7px; '
            f'margin-top: 0; padding: 4px 8px; background: #0E1A14; }}'
        )

        row_layout = QHBoxLayout(group)
        row_layout.setContentsMargins(6, 6, 6, 6)
        row_layout.setSpacing(10)

        # Colored horse indicator
        indicator = _HorseIndicator(horse, color)
        indicator.setFixedSize(36, 36)
        row_layout.addWidget(indicator)

        # Label
        lbl = QLabel(f'Horse {horse}')
        lbl.setFixedWidth(68)
        lbl.setStyleSheet(f'color: {color}; font-weight: bold; font-size: 13px;')
        row_layout.addWidget(lbl)

        # Slider
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setMinimum(0)
        slider.setMaximum(max_pos)
        slider.setValue(cur_pos)
        slider.setTickInterval(1)
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        row_layout.addWidget(slider, stretch=1)

        # Spinbox
        spin = QSpinBox()
        spin.setMinimum(0)
        spin.setMaximum(max_pos)
        spin.setValue(cur_pos)
        spin.setFixedWidth(62)
        row_layout.addWidget(spin)

        # Max label
        max_lbl = QLabel(f'/ {max_pos}')
        max_lbl.setStyleSheet('color: #666; font-size: 11px;')
        row_layout.addWidget(max_lbl)

        # Sync slider ↔ spinbox ↔ game state
        def on_slider(val, _spin=spin, _horse=horse):
            _spin.blockSignals(True)
            _spin.setValue(val)
            _spin.blockSignals(False)
            self._apply(horse, val)

        def on_spin(val, _slider=slider, _horse=horse):
            _slider.blockSignals(True)
            _slider.setValue(val)
            _slider.blockSignals(False)
            self._apply(horse, val)

        slider.valueChanged.connect(on_slider)
        spin.valueChanged.connect(on_spin)

        self._rows[horse] = (slider, spin)
        return group

    # ── Logic ──────────────────────────────────────────────────────────────

    def _apply(self, horse: int, pos: int):
        self.game_state.set_position(horse, pos)
        self.positions_changed.emit()

    def _reset_all(self):
        for horse in HORSE_NUMBERS:
            slider, spin = self._rows[horse]
            for w in (slider, spin):
                w.blockSignals(True)
            slider.setValue(0)
            spin.setValue(0)
            for w in (slider, spin):
                w.blockSignals(False)
            self.game_state.positions[horse] = 0
        self.game_state.winner = None
        if self.game_state.phase == 'done':
            self.game_state.phase = 'racing'
        self.positions_changed.emit()

    def sync_from_state(self):
        """Call this to refresh sliders from current game state."""
        for horse, (slider, spin) in self._rows.items():
            val = self.game_state.positions.get(horse, 0)
            for w in (slider, spin):
                w.blockSignals(True)
            slider.setValue(val)
            spin.setValue(val)
            for w in (slider, spin):
                w.blockSignals(False)


# ── Small colored circle indicator ────────────────────────────────────────────

class _HorseIndicator(QWidget):
    def __init__(self, number: int, color_hex: str, parent=None):
        super().__init__(parent)
        self._number = number
        self._color  = QColor(color_hex)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        r = min(cx, cy) - 2
        grad = QRadialGradient(cx - r * 0.25, cy - r * 0.25, r * 1.4)
        grad.setColorAt(0.0, self._color.lighter(130))
        grad.setColorAt(1.0, self._color.darker(120))
        p.setBrush(grad)
        p.setPen(QPen(QColor(255, 255, 255, 160), 1.5))
        p.drawEllipse(int(cx - r), int(cy - r), int(r * 2), int(r * 2))
        font = QFont('Arial')
        font.setBold(True)
        font.setPointSizeF(max(8.0, r * (0.7 if self._number < 10 else 0.55)))
        p.setFont(font)
        p.setPen(Qt.GlobalColor.white)
        p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, str(self._number))
