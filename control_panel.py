from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)
from PyQt6.QtWidgets import (
    QApplication, QGroupBox, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
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
        self._is_rolling = False
        self._glow_alpha = 0
        self._winner_horse: int = 0
        self._glow_timer = QTimer(self)
        self._glow_timer.setInterval(40)
        self._glow_timer.timeout.connect(self._pulse_glow)
        self.setMinimumSize(120, 80)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def set_roll(self, d1: int, d2: int):
        self._winner_horse = 0
        self.d1, self.d2 = d1, d2
        self.set_rolling_state(False)
        self.update()

    def set_winner(self, horse: int):
        """Switch to winner-display mode — shows a trophy truck instead of dice."""
        self._winner_horse = horse
        self._is_rolling = False
        self._glow_timer.stop()
        self._glow_alpha = 0
        self.update()

    def set_rolling_state(self, rolling: bool):
        self._is_rolling = rolling
        if rolling:
            self._glow_alpha = 60
            self._glow_timer.start()
        else:
            self._glow_timer.stop()
            self._glow_alpha = 0
            self.update()

    def _pulse_glow(self):
        import math, time
        t = time.monotonic()
        self._glow_alpha = int(80 + 120 * abs(math.sin(t * 7)))
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

        # ── Winner mode: show trophy truck instead of dice ────────────────
        if self._winner_horse:
            self._draw_winner(p, w, h)
            p.end()
            return

        gap  = 20
        size = min(h - 20, (w - 3 * gap) // 2)
        x1   = (w // 2) - gap // 2 - size
        x2   = (w // 2) + gap // 2
        y0   = (h - size) // 2

        # Pulsing golden glow when dice are rolling
        if getattr(self, '_is_rolling', False) and self._glow_alpha > 0:
            glow_pen = QPen(QColor(255, 215, 0, self._glow_alpha), max(3, size // 16))
            p.setPen(glow_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            margin = 6
            p.drawRoundedRect(margin, margin, w - 2*margin, h - 2*margin, 12, 12)
            # Inner shimmer fill
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 215, 0, max(0, self._glow_alpha // 5)))
            p.drawRoundedRect(margin, margin, w - 2*margin, h - 2*margin, 12, 12)

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

    def _draw_winner(self, p: QPainter, w: int, h: int):
        """Celebratory winner display: gold panel + trophy + truck number."""
        import math, time

        # Pulsing gold background
        pulse = 0.55 + 0.45 * abs(math.sin(time.monotonic() * 2.5))
        bg = QLinearGradient(0, 0, 0, h)
        bg.setColorAt(0.0, QColor(int(180 * pulse + 40), int(130 * pulse + 20), 0, 230))
        bg.setColorAt(1.0, QColor(int(100 * pulse + 20), int(60  * pulse + 10), 0, 230))
        path = QPainterPath()
        path.addRoundedRect(4, 4, w - 8, h - 8, 10, 10)
        p.setBrush(bg)
        p.setPen(QPen(QColor(255, 220, 50, 200), 2))
        p.drawPath(path)

        # Trophy emoji
        trophy_f = QFont('Segoe UI Emoji')
        trophy_f.setPointSizeF(max(10.0, min(h * 0.28, w * 0.25)))
        p.setFont(trophy_f)
        p.setPen(QColor(255, 255, 255, 240))
        p.drawText(QRectF(0, 6, w, h * 0.48), Qt.AlignmentFlag.AlignCenter, '🏆')

        # "WINNER" text
        win_f = QFont('Georgia')
        win_f.setBold(True)
        win_f.setPointSizeF(max(7.0, min(h * 0.12, w * 0.10)))
        p.setFont(win_f)
        p.setPen(QColor(255, 240, 100, 240))
        p.drawText(QRectF(0, h * 0.46, w, h * 0.24), Qt.AlignmentFlag.AlignCenter, 'WINNER')

        # Truck number
        num_f = QFont('Georgia')
        num_f.setBold(True)
        num_f.setPointSizeF(max(9.0, min(h * 0.18, w * 0.16)))
        p.setFont(num_f)
        p.setPen(QColor(255, 255, 255, 255))
        p.drawText(QRectF(0, h * 0.67, w, h * 0.28), Qt.AlignmentFlag.AlignCenter,
                   f'🚒  #{self._winner_horse}')

        # Trigger repaint for pulse animation
        QTimer.singleShot(60, self.update)

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

                # 🚒 horse marker at leading edge
                emoji_x = bar_x + fill_w
                ef = QFont('Segoe UI Emoji')
                ef.setPointSizeF(max(7.0, bar_h * 0.95))
                p.setFont(ef)
                p.setPen(QColor(255, 255, 255, 230))
                p.drawText(
                    QRectF(emoji_x - 1, cy - icon_w/2, icon_w + 2, icon_w),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, '🚒')

            # ── Winner star ────────────────────────────────────────────────
            if is_w:
                sf = QFont('Segoe UI Emoji')
                sf.setPointSizeF(max(7.0, row_h * 0.42))
                p.setFont(sf)
                p.drawText(
                    QRectF(w - icon_w - 2, cy - row_h/2, icon_w, row_h),
                    Qt.AlignmentFlag.AlignCenter, '🏆')


# ── Race record widget (race count + last 10 winners) ─────────────────────────

class RaceRecordWidget(QWidget):
    """Shows total race count and a list of the last 10 winners."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._race_count = 0
        self._winners = []
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(80)

    def refresh(self):
        from race_history import load_recent_winners
        try:
            self._race_count, self._winners = load_recent_winners(10)
        except Exception:
            pass
        self.update()

    def paintEvent(self, _event):
        from constants import HORSE_COLORS
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = float(self.width()), float(self.height())

        # ── Race count header ─────────────────────────────────────────────
        count_h = h * 0.12
        hdr_grad = QLinearGradient(0, 0, 0, count_h)
        hdr_grad.setColorAt(0.0, QColor('#2A1C08'))
        hdr_grad.setColorAt(1.0, QColor('#1A1006'))
        p.setBrush(hdr_grad)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawRoundedRect(QRectF(0, 0, w, count_h), 4, 4)

        count_pt = max(6.0, min(count_h * 0.48, w * 0.07))
        count_f = QFont('Georgia')
        count_f.setBold(True)
        count_f.setPointSizeF(count_pt)
        p.setFont(count_f)
        p.setPen(QColor('#E8C84A'))
        p.drawText(QRectF(0, 0, w, count_h), Qt.AlignmentFlag.AlignCenter,
                   f'🏁  Total Races: {self._race_count}')

        body_y = count_h + 2
        body_h = h - body_y

        if not self._winners:
            p.setPen(QColor('#806040'))
            nf = QFont('Georgia')
            nf.setItalic(True)
            nf.setPointSizeF(max(6.0, body_h * 0.12))
            p.setFont(nf)
            p.drawText(QRectF(0, body_y, w, body_h),
                       Qt.AlignmentFlag.AlignCenter, 'No races yet')
            p.end()
            return

        # ── Winner rows ───────────────────────────────────────────────────
        rows = len(self._winners)
        row_h = body_h / rows

        # All font sizes derived purely from row_h and w — no fixed minimums that overflow
        rank_pt   = min(row_h * 0.38, w * 0.055)
        truck_pt  = min(row_h * 0.40, w * 0.060)
        rolls_pt  = min(row_h * 0.32, w * 0.048)
        rank_pt   = max(5.0, rank_pt)
        truck_pt  = max(5.0, truck_pt)
        rolls_pt  = max(4.5, rolls_pt)

        rank_f = QFont('Georgia')
        rank_f.setBold(True)
        rank_f.setPointSizeF(rank_pt)

        num_f = QFont('Segoe UI Emoji')
        num_f.setPointSizeF(truck_pt)

        rolls_f = QFont('Consolas')
        rolls_f.setPointSizeF(rolls_pt)

        rank_w  = w * 0.18
        pip_r   = min(row_h * 0.18, w * 0.030)
        truck_x = rank_w + pip_r * 2 + w * 0.03

        for i, rec in enumerate(self._winners):
            ry = body_y + i * row_h
            cy = ry + row_h / 2

            if i % 2 == 0:
                p.setBrush(QColor(30, 20, 8, 100))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawRect(QRectF(0, ry, w, row_h))

            try:
                truck_num = int(rec['winner'])
            except (ValueError, TypeError):
                truck_num = 0
            color = QColor(HORSE_COLORS.get(truck_num, '#C0963A'))

            # Race # (left)
            p.setFont(rank_f)
            p.setPen(QColor('#C8A84B'))
            p.drawText(QRectF(2, ry, rank_w, row_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       f'#{rec["race_num"]}')

            # Colour pip
            p.setBrush(color)
            p.setPen(QPen(color.lighter(130), 1))
            p.drawEllipse(QPointF(rank_w + pip_r + 2, cy), pip_r, pip_r)

            # Truck winner (middle)
            p.setFont(num_f)
            p.setPen(color.lighter(150))
            winner_txt = f'🚒 #{truck_num}' if truck_num else '?'
            p.drawText(QRectF(truck_x, ry, w - truck_x - w * 0.18, row_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, winner_txt)

            # Rolls (right)
            p.setFont(rolls_f)
            p.setPen(QColor('#907050'))
            p.drawText(QRectF(0, ry, w - 4, row_h),
                       Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                       f"{rec['total_rolls']}r")

        p.end()


# ── Compact right-side panel (main window) ─────────────────────────────────────

class CompactRacePanel(QWidget):
    """
    Slim panel that lives in the main window's right strip.
    Shows only the latest dice roll and race standings — no action buttons.
    """

    controls_requested = pyqtSignal()  # emitted when user wants to show/raise Controls window

    def __init__(self, game_state: GameState, parent=None):
        super().__init__(parent)
        self.game_state = game_state
        self.setMinimumWidth(140)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(6)
        root.setContentsMargins(4, 4, 4, 4)

        self.status_lbl = QLabel('🚒  Roll to Start!')
        self.status_lbl.setObjectName('status')
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setWordWrap(True)
        root.addWidget(self.status_lbl)

        dice_grp = QGroupBox('Last Roll')
        dice_grp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        dice_vb = QVBoxLayout(dice_grp)
        dice_vb.setContentsMargins(4, 8, 4, 6)
        self.dice_widget = DiceWidget()
        self.sum_label = QLabel('')
        self.sum_label.setObjectName('sum_label')
        self.sum_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sum_label.setWordWrap(True)
        dice_vb.addWidget(self.dice_widget, stretch=1)
        dice_vb.addWidget(self.sum_label)
        root.addWidget(dice_grp, stretch=2)

        history_grp = QGroupBox('Race Record')
        history_grp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        history_vb = QVBoxLayout(history_grp)
        history_vb.setContentsMargins(4, 8, 4, 4)
        self.race_history_panel = RaceRecordWidget()
        history_vb.addWidget(self.race_history_panel)
        root.addWidget(history_grp, stretch=3)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(4)
        btn_ctrl = QPushButton('📺  Controls')
        btn_ctrl.setToolTip('Raise the Controls window (second screen)')
        btn_ctrl.clicked.connect(self.controls_requested)
        btn_reset_races = QPushButton('🗑  Reset Counter')
        btn_reset_races.setObjectName('btn_reset')
        btn_reset_races.setToolTip('Clear race history and reset the counter to 0')
        btn_reset_races.clicked.connect(self._reset_race_counter)
        btn_row.addWidget(btn_ctrl, stretch=3)
        btn_row.addWidget(btn_reset_races, stretch=2)
        root.addLayout(btn_row)

    def _reset_race_counter(self):
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, 'Reset Race Counter',
            'This will clear all race history and reset the counter to 0.\nAre you sure?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            from race_history import reset_race_history
            reset_race_history()
            self.race_history_panel.refresh()

    def show_roll_animation(self, on_complete=None):
        """Animate dice tumbling fast→slow, then settle on the final result."""
        # fast → medium → slow → very slow (mimics real dice decelerating)
        self._anim_intervals = [30]*4 + [50]*3 + [70]*2 + [100]*2
        self._anim_idx = 0
        self._anim_on_complete = on_complete
        self.dice_widget.set_rolling_state(True)
        if not hasattr(self, '_anim_timer'):
            self._anim_timer = QTimer(self)
            self._anim_timer.setSingleShot(True)
            self._anim_timer.timeout.connect(self._anim_tick)
        self._anim_timer.start(self._anim_intervals[0])

    def stop_animation(self):
        if hasattr(self, '_anim_timer'):
            self._anim_timer.stop()
        self.dice_widget.set_rolling_state(False)

    def _anim_tick(self):
        self.dice_widget.set_rolling()
        self._anim_idx += 1
        if self._anim_idx < len(self._anim_intervals):
            self._anim_timer.start(self._anim_intervals[self._anim_idx])
        else:
            self.dice_widget.set_rolling_state(False)
            cb = self._anim_on_complete
            self._anim_on_complete = None
            if cb:
                cb()

    def refresh(self):
        phase = self.game_state.phase
        winner = getattr(self.game_state, 'winner', None)

        if phase == 'done' and winner:
            self.status_lbl.setText(f'🏆  Truck #{winner} Wins!')
            self.dice_widget.set_winner(winner)
            self.sum_label.setText(f'Total rolls: {len(self.game_state.roll_log)}')
        elif self.game_state.last_roll:
            self.status_lbl.setText('🚒  Race in Progress')
            roll = self.game_state.last_roll
            self.dice_widget.set_roll(*roll)
            self.sum_label.setText(
                f'{roll[0]}  +  {roll[1]}  =  {roll[0]+roll[1]}   →   Truck #{roll[0]+roll[1]}'
            )
        else:
            self.status_lbl.setText('🚒  Roll to Start!')
            self.sum_label.setText('')

        self.race_history_panel.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        status_pt = max(9, min(18, int(w * 0.045)))
        self.status_lbl.setStyleSheet(
            f'font-size: {status_pt}px; font-weight: bold; color: #F5EDD8;'
            f'padding: {max(3, int(w*0.015))}px;'
            f'background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1C6020,stop:1 #0E3C12);'
            f'border: 1px solid #3A8A40; border-radius: 6px;'
        )
        sum_pt = max(8, min(14, int(w * 0.038)))
        self.sum_label.setStyleSheet(
            f'font-size: {sum_pt}px; font-weight: bold; color: #E8C84A; font-family: Georgia, serif;'
        )


# ── Control panel (second-screen window) ──────────────────────────────────────

class ControlPanel(QWidget):
    roll_requested      = pyqtSignal()
    auto_roll_requested = pyqtSignal()
    reset_requested     = pyqtSignal()
    admin_requested     = pyqtSignal()
    webcam_requested    = pyqtSignal()
    history_requested   = pyqtSignal()
    speed_changed       = pyqtSignal(int)   # emits delay in ms

    def __init__(self, game_state: GameState, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.game_state = game_state
        self.setWindowTitle('Truck Dash — Controls')
        self.setMinimumSize(280, 420)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._build()

    def closeEvent(self, event):
        """Closing the controls window hides it rather than destroying it."""
        event.ignore()
        self.hide()

    def show_on_second_screen(self):
        """Position and show on the second screen; fall back to right edge of primary."""
        screens = QApplication.screens()
        if len(screens) >= 2:
            geom = screens[1].availableGeometry()
            w = max(340, min(520, geom.width() // 3))
            h = max(500, min(900, int(geom.height() * 0.80)))
            x = geom.x() + (geom.width() - w) // 2
            y = geom.y() + (geom.height() - h) // 2
            self.setGeometry(x, y, w, h)
        else:
            primary = QApplication.primaryScreen().availableGeometry()
            w = max(320, min(480, primary.width() // 5))
            h = max(500, min(860, int(primary.height() * 0.80)))
            x = primary.right() - w - 10
            y = primary.top() + (primary.height() - h) // 2
            self.setGeometry(x, y, w, h)
        self.show()

    def _build(self):
        root = QVBoxLayout(self)
        root.setSpacing(0)   # spacing set dynamically in resizeEvent
        root.setContentsMargins(8, 8, 8, 8)

        # ── Status label ──────────────────────────────────────────────────
        self.status_lbl = QLabel('🚒  Roll to Start!')
        self.status_lbl.setObjectName('status')
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_lbl.setWordWrap(True)
        root.addWidget(self.status_lbl)

        # ── Dice display ──────────────────────────────────────────────────
        dice_grp = QGroupBox('Dice')
        dice_grp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        dice_vb = QVBoxLayout(dice_grp)
        dice_vb.setContentsMargins(6, 10, 6, 8)
        self.dice_widget = DiceWidget()
        self.sum_label = QLabel('')
        self.sum_label.setObjectName('sum_label')
        self.sum_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.sum_label.setWordWrap(True)
        dice_vb.addWidget(self.dice_widget, stretch=1)
        dice_vb.addWidget(self.sum_label)
        root.addWidget(dice_grp, stretch=2)

        # ── Roll + Auto Roll buttons side by side ─────────────────────────
        roll_row = QHBoxLayout()
        roll_row.setSpacing(6)
        self.btn_roll = QPushButton('🎲   Roll Dice')
        self.btn_roll.setObjectName('btn_roll')
        self.btn_roll.clicked.connect(self.roll_requested)
        self.btn_auto = QPushButton('▶   Auto Roll')
        self.btn_auto.setObjectName('btn_auto')
        self.btn_auto.clicked.connect(self.auto_roll_requested)
        roll_row.addWidget(self.btn_roll, stretch=3)
        roll_row.addWidget(self.btn_auto, stretch=2)
        root.addLayout(roll_row)

        # ── Roll speed slider ─────────────────────────────────────────────
        from PyQt6.QtWidgets import QSlider
        speed_row = QHBoxLayout()
        speed_row.setSpacing(6)
        speed_lbl = QLabel('⏱  Roll Speed:')
        speed_lbl.setObjectName('speed_lbl')
        self._speed_val_lbl = QLabel('1.2s')
        self._speed_val_lbl.setObjectName('speed_val_lbl')
        self._speed_val_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._speed_slider = QSlider(Qt.Orientation.Horizontal)
        self._speed_slider.setMinimum(3)    # 0.3s (fastest)
        self._speed_slider.setMaximum(60)   # 6.0s (slowest)
        self._speed_slider.setValue(12)     # default 1.2s
        self._speed_slider.setTickInterval(6)
        self._speed_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_row.addWidget(speed_lbl, stretch=0)
        speed_row.addWidget(self._speed_slider, stretch=1)
        speed_row.addWidget(self._speed_val_lbl, stretch=0)
        root.addLayout(speed_row)
        self._speed_lbl = speed_lbl

        # ── Race Standings ────────────────────────────────────────────────
        standings_grp = QGroupBox('Race Standings')
        standings_grp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        standings_vb = QVBoxLayout(standings_grp)
        standings_vb.setContentsMargins(6, 10, 6, 6)
        self.standings = HorseStandingsWidget(self.game_state)
        standings_vb.addWidget(self.standings)
        root.addWidget(standings_grp, stretch=3)

        # ── Roll history ──────────────────────────────────────────────────
        history_grp = QGroupBox('Roll History')
        history_grp.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        history_vb = QVBoxLayout(history_grp)
        history_vb.setContentsMargins(4, 10, 4, 4)
        self.history_list = QListWidget()
        self.history_list.setObjectName('history_list')
        history_vb.addWidget(self.history_list)
        root.addWidget(history_grp, stretch=1)

        # ── Utility buttons (2×2 grid) ────────────────────────────────────
        util_grid = QHBoxLayout()
        util_grid.setSpacing(6)

        col1 = QVBoxLayout()
        col1.setSpacing(6)
        self.btn_webcam  = QPushButton('📷  Webcam Dice')
        self.btn_admin   = QPushButton('🛠  Admin Panel')
        self.btn_webcam.clicked.connect(self.webcam_requested)
        self.btn_admin.clicked.connect(self.admin_requested)
        col1.addWidget(self.btn_webcam)
        col1.addWidget(self.btn_admin)

        col2 = QVBoxLayout()
        col2.setSpacing(6)
        self.btn_history = QPushButton('📋  Race History')
        self.btn_reset   = QPushButton('🔄  New Race')
        self.btn_reset.setObjectName('btn_reset')
        self.btn_history.clicked.connect(self.history_requested)
        self.btn_reset.clicked.connect(self.reset_requested)
        col2.addWidget(self.btn_history)
        col2.addWidget(self.btn_reset)

        util_grid.addLayout(col1)
        util_grid.addLayout(col2)
        root.addLayout(util_grid)

        # Store all util buttons for batch resizing
        self._util_btns = [self.btn_webcam, self.btn_admin,
                           self.btn_history, self.btn_reset]

    def _on_speed_changed(self, val: int):
        ms = val * 100
        self._speed_val_lbl.setText(f'{ms/1000:.1f}s')
        self.speed_changed.emit(ms)

    # ── Resize: every element scales with window size ──────────────────────

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()

        # Root layout spacing scales with height
        self.layout().setSpacing(max(3, int(h * 0.007)))

        # ── Status label ──────────────────────────────────────────────────
        sp = max(11, min(42, int(w * 0.032)))
        pad_v = max(4, int(h * 0.008))
        pad_h = max(6, int(w * 0.022))
        self.status_lbl.setStyleSheet(
            f'font-size: {sp}px; font-weight: bold; color: #F5EDD8;'
            f'padding: {pad_v}px {pad_h}px;'
            f'background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1C6020,stop:1 #0E3C12);'
            f'border: 1px solid #3A8A40; border-bottom: 2px solid #082008; border-radius: 8px;'
        )

        # ── Sum label ─────────────────────────────────────────────────────
        sp2 = max(10, min(36, int(w * 0.028)))
        self.sum_label.setStyleSheet(
            f'font-size: {sp2}px; font-weight: bold; color: #E8C84A; font-family: Georgia, serif;'
        )

        # ── Roll button ───────────────────────────────────────────────────
        rp = max(13, min(48, int(w * 0.036)))
        rh = max(40, min(120, int(h * 0.068)))
        self.btn_roll.setStyleSheet(
            f'font-size: {rp}px; min-height: {rh}px;'
            f'background: qlineargradient(x1:0,y1:0,x2:0,y2:1,'
            f'stop:0 #D4A018,stop:0.4 #B08010,stop:0.85 #886008,stop:1 #604006);'
            f'color: #FFF8E0; border: 1px solid #E8C840; border-top: 1px solid #F8E060;'
            f'border-bottom: 3px solid #2A1C00; border-radius: 8px; font-weight: bold;'
            f'font-family: Georgia, serif; padding: {max(4,int(rh*0.12))}px 12px;'
        )

        # ── Auto Roll button ──────────────────────────────────────────────
        ap = max(11, min(36, int(w * 0.028)))
        ah = max(34, min(100, int(h * 0.052)))
        self.btn_auto.setStyleSheet(
            f'font-size: {ap}px; min-height: {ah}px;'
            f'padding: {max(4,int(ah*0.12))}px 10px;'
        )

        # ── Speed slider row ──────────────────────────────────────────────
        slp = max(9, min(22, int(w * 0.024)))
        lbl_style = f'font-size: {slp}px; color: #C8A84B; font-family: Georgia, serif;'
        self._speed_lbl.setStyleSheet(lbl_style)
        self._speed_val_lbl.setStyleSheet(
            f'font-size: {slp}px; font-weight: bold; color: #E8C84A; font-family: Georgia, serif; min-width: {max(28, int(w*0.10))}px;'
        )

        # ── GroupBox title fonts (applied via stylesheet) ─────────────────
        gbp = max(8, min(18, int(w * 0.022)))
        gb_style = (
            f'QGroupBox {{ font-size: {gbp}px; font-weight: bold; color: #C0963A;'
            f'border: 1px solid #3C2A10; border-radius: {max(6,int(w*0.016))}px;'
            f'margin-top: {max(10,int(h*0.018))}px; padding: 4px 4px;'
            f'background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #1A1008,stop:1 #120C06);'
            f'font-family: Georgia, serif; letter-spacing: 0.8px; text-transform: uppercase; }}'
            f'QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left;'
            f'padding: 1px {max(6,int(w*0.016))}px; color: #C8A84B; background: #18100A;'
            f'border: 1px solid #3C2A10; border-radius: 4px; }}'
        )
        for grp in self.findChildren(QGroupBox):
            grp.setStyleSheet(gb_style)

        # ── Utility buttons ───────────────────────────────────────────────
        up = max(10, min(28, int(w * 0.024)))
        uh = max(30, min(80, int(h * 0.046)))
        util_style = (
            f'font-size: {up}px; min-height: {uh}px;'
            f'padding: {max(3,int(uh*0.12))}px 8px;'
        )
        for btn in self._util_btns:
            btn.setStyleSheet(util_style)

        # ── History list font ─────────────────────────────────────────────
        hp = max(9, min(22, int(w * 0.022)))
        font = QFont('Consolas')
        font.setPointSize(hp)
        for i in range(self.history_list.count()):
            item = self.history_list.item(i)
            if item:
                item.setFont(font)

    # ── Public refresh ─────────────────────────────────────────────────────

    def refresh(self, auto_rolling: bool = False):
        phase = self.game_state.phase
        racing = phase == 'racing'
        self.btn_roll.setEnabled(racing and not auto_rolling)
        self.btn_auto.setEnabled(racing or auto_rolling)
        self.btn_auto.setText('⏹   Stop Auto' if auto_rolling else '▶   Auto Roll')

        if phase == 'done' and self.game_state.winner:
            self.status_lbl.setText(f'🏆  Truck #{self.game_state.winner} Wins!')
        elif self.game_state.last_roll:
            r = self.game_state.last_roll
            self.status_lbl.setText(f'🚒  Race in Progress')
        else:
            self.status_lbl.setText('🚒  Roll to Start!')

        roll = self.game_state.last_roll
        if roll:
            self.dice_widget.set_roll(*roll)
            self.sum_label.setText(
                f'{roll[0]}  +  {roll[1]}  =  {roll[0]+roll[1]}   →   Truck #{roll[0]+roll[1]}'
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
        pt = max(9, min(22, int(self.width() * 0.022)))
        font = QFont('Consolas')
        font.setPointSize(pt)
        for d1, d2 in reversed(log[-50:]):
            item = QListWidgetItem(f'  {d1} + {d2} = {d1+d2}   →  Truck #{d1+d2}')
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
