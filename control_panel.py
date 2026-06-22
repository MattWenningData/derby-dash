from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)
from PyQt6.QtWidgets import (
    QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from constants import HORSE_COLORS, HORSE_NUMBERS, TRACK_LENGTHS
from game_state import GameState


# ── 3-D Dice widget ────────────────────────────────────────────────────────────

class DiceWidget(QWidget):
    """Custom-painted pair of realistic ivory dice."""

    _PIPS = {
        1: [(0.5,  0.5)],
        2: [(0.28, 0.28), (0.72, 0.72)],
        3: [(0.28, 0.28), (0.5,  0.5),  (0.72, 0.72)],
        4: [(0.28, 0.28), (0.72, 0.28), (0.28, 0.72), (0.72, 0.72)],
        5: [(0.28, 0.28), (0.72, 0.28), (0.5,  0.5),  (0.28, 0.72), (0.72, 0.72)],
        6: [(0.28, 0.2),  (0.72, 0.2),  (0.28, 0.5),  (0.72, 0.5),  (0.28, 0.8),  (0.72, 0.8)],
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.d1: int = 0
        self.d2: int = 0
        self.setMinimumSize(120, 80)
        # No maximum height — expands freely on large screens
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_roll(self, d1: int, d2: int):
        self.d1, self.d2 = d1, d2
        self.update()

    def set_rolling(self):
        import secrets
        self.d1 = secrets.randbelow(6) + 1
        self.d2 = secrets.randbelow(6) + 1
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        gap  = 20
        size = min(h - 20, (w - 3 * gap) // 2)
        x1   = (w // 2) - gap // 2 - size
        x2   = (w // 2) + gap // 2
        y0   = (h - size) // 2

        # Left die — straight
        self._draw_die(p, x1, y0, size, self.d1)

        # Right die — slightly tilted for a "just thrown" feel
        p.save()
        p.translate(x2 + size / 2, y0 + size / 2)
        p.rotate(8)
        p.translate(-(size / 2), -(size / 2))
        self._draw_die(p, 0, 0, size, self.d2)
        p.restore()

        p.end()

    def _draw_die(self, p: QPainter, x: int, y: int, size: int, value: int):
        r = max(7, size // 8)

        # Soft drop shadow
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        shadow_path = QPainterPath()
        shadow_path.addRoundedRect(x + 5, y + 7, size, size, r, r)
        p.drawPath(shadow_path)

        # Bottom/right side face — darker for 3-D depth
        depth = max(4, size // 14)
        side_grad = QLinearGradient(x, y + size, x + size, y + size)
        side_grad.setColorAt(0.0, QColor('#A08040'))
        side_grad.setColorAt(1.0, QColor('#705010'))
        side_path = QPainterPath()
        side_path.addRoundedRect(x + depth, y + depth, size, size, r, r)
        p.setBrush(side_grad)
        p.drawPath(side_path)

        # Top face — warm ivory with subtle gradient
        face_grad = QLinearGradient(x, y, x + size, y + size)
        face_grad.setColorAt(0.0, QColor('#FBF7EC'))
        face_grad.setColorAt(0.5, QColor('#F5EDD8'))
        face_grad.setColorAt(1.0, QColor('#EDE0C0'))
        face_path = QPainterPath()
        face_path.addRoundedRect(x, y, size, size, r, r)
        p.setBrush(face_grad)
        p.setPen(QPen(QColor('#B89840'), 1.5))
        p.drawPath(face_path)

        # Edge highlight (top-left rim)
        rim = QPainterPath()
        rim.addRoundedRect(x + 1, y + 1, size - 2, size - 2, r, r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 100), 1.0))
        p.drawPath(rim)

        if value < 1 or value > 6:
            font = QFont('Georgia')
            font.setBold(True)
            font.setPointSizeF(size * 0.32)
            p.setFont(font)
            p.setPen(QColor('#B8A070'))
            p.drawText(QRectF(x, y, size, size), Qt.AlignmentFlag.AlignCenter, '?')
            return

        # Pips
        pad   = size * 0.13
        inner = size - 2 * pad
        pr    = max(3.5, size * 0.092)
        for (nx, ny) in self._PIPS.get(value, []):
            cx = x + pad + nx * inner
            cy = y + pad + ny * inner
            # Recessed shadow
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 50))
            p.drawEllipse(QRectF(cx - pr + 1, cy - pr + 1.5, pr * 2, pr * 2))
            # Pip body
            grad = QRadialGradient(cx - pr * 0.2, cy - pr * 0.25, pr * 1.3)
            grad.setColorAt(0.0, QColor('#3A2A10'))
            grad.setColorAt(0.7, QColor('#1A0E04'))
            grad.setColorAt(1.0, QColor('#0A0400'))
            p.setBrush(grad)
            p.drawEllipse(QRectF(cx - pr, cy - pr, pr * 2, pr * 2))


# ── Horse standings custom-painted widget ─────────────────────────────────────

class HorseStandingsWidget(QWidget):
    """Compact race progress bars for all 11 horses."""

    def __init__(self, game_state: GameState, parent=None):
        super().__init__(parent)
        self.game_state = game_state
        self.setMinimumHeight(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def refresh(self):
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        w, h    = self.width(), self.height()
        n       = len(HORSE_NUMBERS)
        row_h   = h / n
        label_w = 30.0
        bar_x   = label_w + 5.0
        icon_w  = max(16.0, row_h * 0.55)   # space for horse emoji marker
        bar_w   = w - bar_x - icon_w - 4.0
        bar_h   = max(9.0, row_h * 0.50)
        winner  = getattr(self.game_state, 'winner', None)

        for idx, horse in enumerate(HORSE_NUMBERS):
            cy    = idx * row_h + row_h / 2.0
            pos   = self.game_state.positions.get(horse, 0)
            maxi  = TRACK_LENGTHS[horse]
            pct   = pos / maxi if maxi > 0 else 0.0
            color = QColor(HORSE_COLORS[horse])
            is_w  = (winner == horse)

            # ── Row separator ──────────────────────────────────────────────
            if idx > 0:
                p.setPen(QPen(QColor(60, 35, 10, 60), 1))
                p.drawLine(QPointF(0, idx * row_h), QPointF(w, idx * row_h))

            # ── Number label ───────────────────────────────────────────────
            font = QFont('Georgia')
            font.setBold(True)
            font.setPointSizeF(max(7.0, row_h * 0.34))
            p.setFont(font)
            p.setPen(QColor('#FFD700') if is_w else color.lighter(130))
            p.drawText(QRectF(0, cy - row_h/2, label_w, row_h),
                       Qt.AlignmentFlag.AlignCenter, str(horse))

            # ── Track groove ───────────────────────────────────────────────
            track_rect = QRectF(bar_x, cy - bar_h/2, bar_w, bar_h)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(12, 8, 3, 200))
            p.drawRoundedRect(track_rect, bar_h/2, bar_h/2)
            # Inner groove shadow
            inner_rect = QRectF(bar_x + 1, cy - bar_h/2 + 1, bar_w - 2, bar_h/2)
            p.setBrush(QColor(0, 0, 0, 40))
            p.drawRect(inner_rect)

            # ── Filled progress bar ────────────────────────────────────────
            if pos > 0:
                fill_w = max(bar_h, pct * bar_w)
                fill   = QRectF(bar_x, cy - bar_h/2, fill_w, bar_h)
                if is_w:
                    bg = QLinearGradient(bar_x, cy - bar_h/2, bar_x, cy + bar_h/2)
                    bg.setColorAt(0.0, QColor('#FFE066'))
                    bg.setColorAt(0.45, QColor('#E8C840'))
                    bg.setColorAt(1.0, QColor('#A07808'))
                else:
                    bg = QLinearGradient(bar_x, cy - bar_h/2, bar_x, cy + bar_h/2)
                    bg.setColorAt(0.0, color.lighter(140))
                    bg.setColorAt(0.45, color)
                    bg.setColorAt(1.0, color.darker(155))
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(bg)
                p.drawRoundedRect(fill, bar_h/2, bar_h/2)

                # Shine line on bar
                shine = QLinearGradient(bar_x, cy - bar_h/2, bar_x, cy - bar_h/2 + bar_h*0.4)
                shine.setColorAt(0.0, QColor(255, 255, 255, 70))
                shine.setColorAt(1.0, QColor(255, 255, 255, 0))
                p.setBrush(shine)
                p.drawRoundedRect(
                    QRectF(bar_x + 1, cy - bar_h/2 + 1, fill_w - 2, bar_h*0.45),
                    bar_h/2, bar_h/2)

                # Position fraction text inside bar
                if fill_w > 22:
                    p.setFont(QFont('Arial', max(5, int(bar_h * 0.52))))
                    p.setPen(QColor(255, 255, 255, 200))
                    p.drawText(fill, Qt.AlignmentFlag.AlignCenter, f'{pos}/{maxi}')

                # 🏇 horse marker at leading edge
                emoji_x = bar_x + fill_w
                ef = QFont('Segoe UI Emoji')
                ef.setPointSizeF(max(7.0, bar_h * 0.95))
                p.setFont(ef)
                p.setPen(QColor(255, 255, 255, 230))
                p.drawText(
                    QRectF(emoji_x - 1, cy - icon_w/2, icon_w + 2, icon_w),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, '🏇')

            # ── Winner star ────────────────────────────────────────────────
            if is_w:
                sf = QFont('Segoe UI Emoji')
                sf.setPointSizeF(max(7.0, row_h * 0.42))
                p.setFont(sf)
                p.drawText(
                    QRectF(w - icon_w - 2, cy - row_h/2, icon_w, row_h),
                    Qt.AlignmentFlag.AlignCenter, '🏆')


# ── Control panel (right sidebar) ─────────────────────────────────────────────

class ControlPanel(QWidget):
    roll_requested   = pyqtSignal()
    reset_requested  = pyqtSignal()
    admin_requested  = pyqtSignal()
    webcam_requested = pyqtSignal()
    history_requested = pyqtSignal()

    def __init__(self, game_state: GameState, parent=None):
        super().__init__(parent)
        self.game_state = game_state
        # No fixed width — scales with stretch ratio from main layout
        self.setMinimumWidth(240)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(8)
        root.setContentsMargins(4, 4, 4, 4)

        # ── Status label ──────────────────────────────────────────────────
        self.status_lbl = QLabel('🏇  Roll to Start!')
        self.status_lbl.setObjectName('status')
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setWordWrap(True)
        root.addWidget(self.status_lbl)

        # ── Dice display — stretch=2: grows with screen ───────────────────
        dice_grp = QGroupBox('Dice')
        dice_grp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        dice_vb  = QVBoxLayout(dice_grp)
        dice_vb.setContentsMargins(6, 10, 6, 8)
        self.dice_widget = DiceWidget()
        self.sum_label   = QLabel('')
        self.sum_label.setObjectName('sum_label')
        self.sum_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sum_label.setWordWrap(True)
        dice_vb.addWidget(self.dice_widget, stretch=1)
        dice_vb.addWidget(self.sum_label)
        root.addWidget(dice_grp, stretch=2)

        # ── Roll button ───────────────────────────────────────────────────
        self.btn_roll = QPushButton('🎲   Roll Dice')
        self.btn_roll.setObjectName('btn_roll')
        self.btn_roll.clicked.connect(self.roll_requested)
        self.btn_roll.setMinimumHeight(54)
        root.addWidget(self.btn_roll)

        # ── Horse standings — stretch=3: largest section ──────────────────
        standings_grp = QGroupBox('Race Standings')
        standings_grp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        standings_vb  = QVBoxLayout(standings_grp)
        standings_vb.setContentsMargins(6, 10, 6, 6)
        self.standings = HorseStandingsWidget(self.game_state)
        standings_vb.addWidget(self.standings)
        root.addWidget(standings_grp, stretch=3)

        # ── Roll history — stretch=1: grows but stays compact ─────────────
        history_grp = QGroupBox('Roll History')
        history_grp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        history_vb  = QVBoxLayout(history_grp)
        history_vb.setContentsMargins(4, 10, 4, 4)
        self.history_list = QListWidget()
        self.history_list.setObjectName('history_list')
        history_vb.addWidget(self.history_list)
        root.addWidget(history_grp, stretch=1)

        # ── Utility buttons ───────────────────────────────────────────────
        btn_webcam = QPushButton('📷   Webcam Dice')
        btn_webcam.clicked.connect(self.webcam_requested)

        btn_history = QPushButton('📋   Race History')
        btn_history.clicked.connect(self.history_requested)

        btn_admin = QPushButton('🛠   Admin Panel')
        btn_admin.clicked.connect(self.admin_requested)

        btn_reset = QPushButton('🔄   New Race')
        btn_reset.setObjectName('btn_reset')
        btn_reset.clicked.connect(self.reset_requested)

        for btn in (btn_webcam, btn_history, btn_admin, btn_reset):
            btn.setMinimumHeight(40)
            root.addWidget(btn)

    # ── Resize: scale fonts with panel width ───────────────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        # Status label font
        status_pt = max(11, int(w * 0.042))
        self.status_lbl.setStyleSheet(
            f'font-size: {status_pt}px; font-weight: bold; color: #F5EDD8;'
            f'padding: {max(4, int(w*0.016))}px {max(6, int(w*0.03))}px;'
            f'background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1C6020,stop:1 #0E3C12);'
            f'border: 1px solid #3A8A40; border-bottom: 2px solid #082008; border-radius: 8px;'
        )
        # Sum label font
        sum_pt = max(10, int(w * 0.036))
        self.sum_label.setStyleSheet(
            f'font-size: {sum_pt}px; font-weight: bold; color: #E8C84A; font-family: Georgia, serif;'
        )
        # Roll button font
        roll_pt = max(13, int(w * 0.052))
        roll_h  = max(54, int(w * 0.16))
        self.btn_roll.setStyleSheet(
            f'font-size: {roll_pt}px; min-height: {roll_h}px;'
            f'background: qlineargradient(x1:0,y1:0,x2:0,y2:1,'
            f'stop:0 #D4A018,stop:0.4 #B08010,stop:0.85 #886008,stop:1 #604006);'
            f'color: #FFF8E0; border: 1px solid #E8C840; border-top: 1px solid #F8E060;'
            f'border-bottom: 3px solid #2A1C00; border-radius: 9px; font-weight: bold;'
            f'font-family: Georgia, serif; padding: {max(8,int(w*0.025))}px 18px;'
        )

    # ── Public refresh ─────────────────────────────────────────────────────

    def refresh(self):
        phase = self.game_state.phase
        self.btn_roll.setEnabled(phase == 'racing')

        if phase == 'done' and self.game_state.winner:
            self.status_lbl.setText(f'🏆  Horse #{self.game_state.winner} Wins!')
        elif self.game_state.last_roll:
            r = self.game_state.last_roll
            self.status_lbl.setText(f'🏇  Race in Progress')
        else:
            self.status_lbl.setText('🏇  Roll to Start!')

        roll = self.game_state.last_roll
        if roll:
            self.dice_widget.set_roll(*roll)
            self.sum_label.setText(
                f'{roll[0]}  +  {roll[1]}  =  {roll[0]+roll[1]}   →   Horse #{roll[0]+roll[1]}'
            )
        else:
            self.sum_label.setText('')

        self.standings.refresh()
        self._sync_history()

    def _sync_history(self):
        log = self.game_state.roll_log
        current_count = self.history_list.count()
        if len(log) == current_count:
            return
        self.history_list.clear()
        pt = max(9, int(self.width() * 0.032))
        font = QFont('Consolas')
        font.setPointSize(pt)
        for d1, d2 in reversed(log[-30:]):
            item = QListWidgetItem(f'  {d1} + {d2} = {d1+d2}   →  Horse #{d1+d2}')
            item.setForeground(QColor(HORSE_COLORS.get(d1 + d2, '#F0EAD6')))
            item.setFont(font)
            self.history_list.addItem(item)

    def show_roll_animation(self):
        self._anim_count = 0
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(75)
        self._anim_timer.timeout.connect(self._anim_tick)
        self._anim_timer.start()

    def _anim_tick(self):
        self._anim_count += 1
        self.dice_widget.set_rolling()
        if self._anim_count >= 6:
            self._anim_timer.stop()
            roll = self.game_state.last_roll
            if roll:
                self.dice_widget.set_roll(*roll)
