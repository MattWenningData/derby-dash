from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import (
    QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient,
)
from PyQt6.QtWidgets import QWidget

from constants import HORSE_COLORS, HORSE_NUMBERS, TRACK_LENGTHS


class BoardWidget(QWidget):
    def __init__(self, game_state, parent=None):
        super().__init__(parent)
        self.game_state = game_state
        self._pulse = False
        self.setMinimumSize(640, 400)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(550)
        self._pulse_timer.timeout.connect(self._on_pulse_timer)
        self._pulse_timer.start()

    def refresh(self):
        self.update()

    def _on_pulse_timer(self):
        if getattr(self.game_state, 'phase', None) == 'done' and getattr(self.game_state, 'winner', None):
            self._pulse = not self._pulse
            self.update()
        elif self._pulse:
            self._pulse = False
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        outer_rect  = QRectF(self.rect()).adjusted(6, 6, -6, -6)
        border_w    = 16.0
        corner_r    = 18.0

        board_path  = QPainterPath()
        board_path.addRoundedRect(outer_rect, corner_r, corner_r)

        self._draw_board_background(painter, outer_rect, board_path)

        inner       = outer_rect.adjusted(border_w, border_w, -border_w, -border_w)
        title_h     = max(58.0, inner.height() * 0.135)
        footer_h    = max(28.0, inner.height() * 0.068)

        title_rect  = QRectF(inner.left(), inner.top(), inner.width(), title_h)
        race_rect   = QRectF(inner.left(), inner.top() + title_h,
                             inner.width(), inner.height() - title_h - footer_h)
        footer_rect = QRectF(inner.left(), race_rect.bottom(), inner.width(), footer_h)

        self._draw_title_bar(painter, title_rect, board_path)
        self._draw_race_board(painter, race_rect)
        self._draw_footer(painter, footer_rect, race_rect)

    # ── Board outer frame ──────────────────────────────────────────────────────

    def _draw_board_background(self, painter: QPainter, rect: QRectF, path: QPainterPath):
        # Rich walnut wood gradient
        g = QLinearGradient(rect.topLeft(), rect.bottomRight())
        g.setColorAt(0.00, QColor('#CA9640'))
        g.setColorAt(0.35, QColor('#B87A2C'))
        g.setColorAt(0.70, QColor('#9A6018'))
        g.setColorAt(1.00, QColor('#784808'))
        painter.fillPath(path, g)

        # Wood grain streaks
        painter.save()
        painter.setClipPath(path)
        n = max(24, int(rect.width() / 24))
        for i in range(n + 1):
            x = rect.left() + rect.width() * i / n
            painter.setPen(QPen(QColor(255, 235, 175, 20 if i % 3 == 0 else 9), 1))
            painter.drawLine(QPointF(x, rect.top()), QPointF(x + rect.width()*0.014, rect.bottom()))
            painter.setPen(QPen(QColor(70, 30, 4, 15 if i % 4 == 0 else 7), 1))
            painter.drawLine(QPointF(x+2, rect.top()), QPointF(x - rect.width()*0.009, rect.bottom()))
        painter.restore()

        # Dark border bevel
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#3C1E06'), 16, Qt.PenStyle.SolidLine,
                            Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        painter.drawPath(path)
        # Inner gold rim
        inner_path = QPainterPath()
        inner_path.addRoundedRect(rect.adjusted(4, 4, -4, -4), 14, 14)
        painter.setPen(QPen(QColor(200, 155, 60, 90), 1.5))
        painter.drawPath(inner_path)

    # ── Title bar ─────────────────────────────────────────────────────────────

    def _draw_title_bar(self, painter: QPainter, rect: QRectF, board_path: QPainterPath):
        g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        g.setColorAt(0.0, QColor('#185A1C'))
        g.setColorAt(1.0, QColor('#0C3410'))
        painter.save()
        painter.setClipPath(board_path)
        painter.fillRect(rect, g)
        painter.restore()

        # Decorative double line at bottom
        for offset, alpha in ((0, 200), (3, 80)):
            sep = QLinearGradient(rect.bottomLeft(), rect.bottomRight())
            sep.setColorAt(0.0, QColor(0, 0, 0, 0))
            sep.setColorAt(0.5, QColor(210, 165, 50, alpha))
            sep.setColorAt(1.0, QColor(0, 0, 0, 0))
            painter.setPen(QPen(sep, 1.5))
            y = rect.bottom() - offset
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        # Small diamond ornaments
        painter.setBrush(QColor(210, 165, 50, 160))
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        for x_frac in (0.12, 0.88):
            cx = rect.left() + rect.width() * x_frac
            cy = rect.center().y()
            sz = min(8.0, rect.height() * 0.18)
            diamond = QPainterPath()
            diamond.moveTo(cx, cy - sz)
            diamond.lineTo(cx + sz * 0.65, cy)
            diamond.lineTo(cx, cy + sz)
            diamond.lineTo(cx - sz * 0.65, cy)
            diamond.closeSubpath()
            painter.drawPath(diamond)

        # Title
        font = QFont('Georgia')
        font.setItalic(True)
        font.setBold(True)
        font.setPointSizeF(max(18.0, rect.height() * 0.44))
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3.0)
        painter.setFont(font)
        painter.setPen(QColor(60, 35, 0, 140))
        painter.drawText(rect.translated(1.5, 2.5), Qt.AlignmentFlag.AlignCenter, '🏇  DERBY DASH')
        painter.setPen(QColor('#EAC848'))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, '🏇  DERBY DASH')

    # ── Main race board ───────────────────────────────────────────────────────

    def _draw_race_board(self, painter: QPainter, rect: QRectF):
        gate_w   = max(64.0, min(90.0, rect.width() * 0.088))
        finish_w = max(60.0, min(82.0, rect.width() * 0.078))

        gate_rect   = QRectF(rect.left(), rect.top(), gate_w, rect.height())
        finish_rect = QRectF(rect.right() - finish_w, rect.top(), finish_w, rect.height())
        track_rect  = QRectF(gate_rect.right(), rect.top(),
                             rect.width() - gate_w - finish_w, rect.height())

        n           = len(HORSE_NUMBERS)
        lane_h      = rect.height() / n
        hole_r      = max(6.0, lane_h * 0.26)           # no upper cap — scales with screen
        piece_r     = hole_r * 1.54
        margin      = piece_r + 9.0
        race_start  = track_rect.left() + margin
        race_w      = max(10.0, track_rect.width() - margin * 2.0)

        # ── Green felt lane backgrounds ────────────────────────────────────
        felt = [QColor('#0C3A0F'), QColor('#0E4412')]
        for i in range(n):
            ly = rect.top() + i * lane_h
            lr = QRectF(track_rect.left(), ly, track_rect.width(), lane_h)
            painter.fillRect(lr, felt[i % 2])
            # Horizontal felt grain lines
            painter.setPen(QPen(QColor(255, 255, 255, 4), 1))
            for s in range(max(2, int(lane_h / 5))):
                fy = ly + s * (lane_h / max(2, int(lane_h / 5)))
                painter.drawLine(QPointF(track_rect.left(), fy), QPointF(track_rect.right(), fy))

        # ── Gate (starting gate bars) ──────────────────────────────────────
        gg = QLinearGradient(gate_rect.topLeft(), gate_rect.topRight())
        gg.setColorAt(0.0, QColor('#1E6822'))
        gg.setColorAt(1.0, QColor('#123E14'))
        painter.fillRect(gate_rect, gg)

        # Gate horizontal bars per lane
        bar_pen = QPen(QColor(0, 0, 0, 90), 1.5)
        painter.setPen(bar_pen)
        for i in range(1, n):
            gy = rect.top() + i * lane_h
            painter.drawLine(QPointF(gate_rect.left(), gy), QPointF(gate_rect.right(), gy))
        # Gate latch details (small rectangles on the right edge)
        painter.setBrush(QColor(180, 140, 40, 140))
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        for i in range(n):
            ly = rect.top() + i * lane_h
            latch_h = lane_h * 0.22
            latch_y = ly + (lane_h - latch_h) / 2
            painter.drawRoundedRect(
                QRectF(gate_rect.right() - 6, latch_y, 5, latch_h), 2, 2)
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.drawLine(gate_rect.topRight(), gate_rect.bottomRight())

        # ── Finish column (checkered flag) ─────────────────────────────────
        self._draw_checkered_finish(painter, finish_rect)

        # ── Quarter-mark progress ticks on track ─────────────────────────
        painter.setPen(QPen(QColor(255, 255, 255, 22), 1, Qt.PenStyle.DashLine))
        for frac in (0.25, 0.50, 0.75):
            tx = race_start + frac * race_w
            painter.drawLine(QPointF(tx, track_rect.top() + 2), QPointF(tx, track_rect.bottom() - 2))

        # ── Lane dividers ──────────────────────────────────────────────────
        painter.setPen(QPen(QColor(0, 0, 0, 70), 1))
        for i in range(1, n):
            y = rect.top() + i * lane_h
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        # ── Finish dashed marker line ──────────────────────────────────────
        fx  = race_start + race_w
        pen = QPen(QColor(255, 255, 200, 200), 2, Qt.PenStyle.DashLine)
        pen.setDashPattern([5, 3])
        painter.setPen(pen)
        painter.drawLine(QPointF(fx, track_rect.top() + 4), QPointF(fx, track_rect.bottom() - 4))

        # ── Inner board shadow (edges of track area feel recessed) ─────────
        painter.save()
        edge_shadow = QLinearGradient(track_rect.topLeft(), QPointF(track_rect.left() + 22, track_rect.top()))
        edge_shadow.setColorAt(0.0, QColor(0, 0, 0, 55))
        edge_shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(QRectF(track_rect.left(), track_rect.top(), 22, track_rect.height()), edge_shadow)
        edge_shadow2 = QLinearGradient(track_rect.topRight(), QPointF(track_rect.right() - 22, track_rect.top()))
        edge_shadow2.setColorAt(0.0, QColor(0, 0, 0, 55))
        edge_shadow2.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.fillRect(QRectF(track_rect.right() - 22, track_rect.top(), 22, track_rect.height()), edge_shadow2)
        painter.restore()

        # ── Gate horse number labels ───────────────────────────────────────
        nfont = QFont('Georgia')
        nfont.setBold(True)
        nfont.setPointSizeF(max(11.0, lane_h * 0.40))
        for i, horse in enumerate(HORSE_NUMBERS):
            lane_rect = QRectF(gate_rect.left(), rect.top() + i * lane_h, gate_w, lane_h)
            color = QColor(HORSE_COLORS[horse])
            painter.setFont(nfont)
            painter.setPen(QColor(0, 0, 0, 110))
            painter.drawText(lane_rect.translated(1, 1.5), Qt.AlignmentFlag.AlignCenter, str(horse))
            painter.setPen(color.lighter(145))
            painter.drawText(lane_rect, Qt.AlignmentFlag.AlignCenter, str(horse))

        # ── FINISH rotated label ───────────────────────────────────────────
        ff = QFont('Georgia')
        ff.setBold(True)
        ff.setItalic(True)
        ff.setPointSizeF(max(9.0, finish_rect.width() * 0.26))
        painter.save()
        painter.translate(finish_rect.center())
        painter.rotate(-90)
        painter.setFont(ff)
        painter.setPen(QColor(255, 255, 255, 220))
        painter.drawText(
            QRectF(-finish_rect.height()/2, -finish_rect.width()/2,
                   finish_rect.height(), finish_rect.width()),
            Qt.AlignmentFlag.AlignCenter, 'FINISH')
        painter.restore()

        # ── Pass 1: draw all holes ─────────────────────────────────────────
        for i, horse in enumerate(HORSE_NUMBERS):
            cy   = rect.top() + i * lane_h + lane_h / 2.0
            tlen = TRACK_LENGTHS[horse]
            for step in range(tlen + 1):
                x = race_start + step * race_w / tlen
                self._draw_hole(painter, QPointF(x, cy), hole_r)

        # ── Pass 2: draw all horse pieces on top ───────────────────────────
        for i, horse in enumerate(HORSE_NUMBERS):
            cy      = rect.top() + i * lane_h + lane_h / 2.0
            tlen    = TRACK_LENGTHS[horse]
            raw_pos = int(getattr(self.game_state, 'positions', {}).get(horse, 0))
            pos     = max(0, min(raw_pos, tlen))
            px      = race_start + pos * race_w / tlen
            winner  = (getattr(self.game_state, 'winner', None) == horse and raw_pos >= tlen)
            self._draw_horse_piece(painter, horse, QPointF(px, cy), piece_r, winner, finish_rect)

    def _draw_checkered_finish(self, painter: QPainter, rect: QRectF):
        cell = max(8.0, min(13.0, rect.width() / 4.2))
        cols = max(2, int(rect.width()  / cell) + 1)
        rows = max(2, int(rect.height() / cell) + 1)
        painter.save()
        painter.setClipRect(rect)
        for row in range(rows):
            for col in range(cols):
                x = rect.left() + col * cell
                y = rect.top()  + row * cell
                c = QColor(238, 238, 238) if (row + col) % 2 == 0 else QColor(22, 22, 22)
                painter.fillRect(QRectF(x, y, cell, cell), c)
        # Subtle dark tint overlay
        painter.fillRect(rect, QColor(10, 40, 10, 48))
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawLine(rect.topLeft(), rect.bottomLeft())
        painter.restore()

    # ── Footer ─────────────────────────────────────────────────────────────────

    def _draw_footer(self, painter: QPainter, rect: QRectF, race_rect: QRectF):
        sep = QLinearGradient(rect.topLeft(), rect.topRight())
        sep.setColorAt(0.0, QColor(0, 0, 0, 0))
        sep.setColorAt(0.5, QColor('#C8A84B'))
        sep.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setPen(QPen(sep, 1.5))
        painter.drawLine(rect.topLeft(), rect.topRight())

        # Label widths match the gate/finish column widths so they sit directly
        # beneath the columns at any screen size (same formula as _draw_race_board).
        gate_w   = max(64.0, min(90.0, race_rect.width() * 0.088))
        finish_w = max(60.0, min(82.0, race_rect.width() * 0.078))

        # Font scales with footer height; clamp so text never overflows its box.
        font_pt  = min(rect.height() * 0.52,
                       gate_w   * 0.30,    # won't overflow START box
                       finish_w * 0.30)    # won't overflow FINISH box
        font_pt  = max(7.0, font_pt)

        font = QFont('Georgia')
        font.setItalic(True)
        font.setBold(True)
        font.setPointSizeF(font_pt)
        painter.setFont(font)
        painter.setPen(QColor('#C8A84B'))

        start_box  = QRectF(race_rect.left(),              rect.top(), gate_w,   rect.height())
        finish_box = QRectF(race_rect.right() - finish_w,  rect.top(), finish_w, rect.height())

        # Drop-shadow offset for readability
        shadow_col = QColor(0, 0, 0, 130)
        painter.setPen(shadow_col)
        painter.drawText(start_box.translated(1, 1.5),
                         Qt.AlignmentFlag.AlignCenter, 'START')
        painter.drawText(finish_box.translated(1, 1.5),
                         Qt.AlignmentFlag.AlignCenter, 'FINISH')

        painter.setPen(QColor('#C8A84B'))
        painter.drawText(start_box,  Qt.AlignmentFlag.AlignCenter, 'START')
        painter.drawText(finish_box, Qt.AlignmentFlag.AlignCenter, 'FINISH')

        last_roll = getattr(self.game_state, 'last_roll', None)
        if last_roll:
            rf = QFont('Georgia')
            rf.setPointSizeF(max(8.0, rect.height() * 0.42))
            painter.setFont(rf)
            painter.setPen(QColor('#C8A84B'))
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter,
                             f'Last roll:  {last_roll[0]}  +  {last_roll[1]}  =  {last_roll[0]+last_roll[1]}')

    # ── Hole ───────────────────────────────────────────────────────────────────

    def _draw_hole(self, painter: QPainter, center: QPointF, r: float):
        painter.save()
        painter.setPen(QPen(Qt.PenStyle.NoPen))

        # Outer rim shadow
        rim_g = QRadialGradient(center, r * 1.22)
        rim_g.setColorAt(0.55, QColor(0, 0, 0, 0))
        rim_g.setColorAt(0.80, QColor(0, 0, 0, 100))
        rim_g.setColorAt(1.00, QColor(0, 0, 0, 0))
        painter.setBrush(rim_g)
        painter.drawEllipse(center, r * 1.25, r * 1.25)

        # Cavity
        cav = QRadialGradient(QPointF(center.x() - r*0.18, center.y() - r*0.18), r)
        cav.setColorAt(0.00, QColor('#5A2A06'))
        cav.setColorAt(0.45, QColor('#28100A'))
        cav.setColorAt(0.85, QColor('#0A0402'))
        cav.setColorAt(1.00, QColor('#000000'))
        painter.setBrush(cav)
        painter.drawEllipse(center, r, r)

        # Inner depth rings
        for size, alpha in ((0.72, 60), (0.46, 50)):
            painter.setBrush(QColor(0, 0, 0, alpha))
            painter.drawEllipse(center, r*size, r*size)

        # Rim highlight
        hi = QRadialGradient(QPointF(center.x() - r*0.52, center.y() - r*0.52), r*0.85)
        hi.setColorAt(0.0, QColor(255, 215, 130, 65))
        hi.setColorAt(1.0, QColor(255, 215, 130, 0))
        painter.setBrush(hi)
        painter.drawEllipse(center, r, r)
        painter.restore()

    # ── Horse piece ────────────────────────────────────────────────────────────

    def _draw_horse_piece(self, painter: QPainter, horse: int, center: QPointF,
                          radius: float, is_winner: bool, finish_rect: QRectF):
        painter.save()
        painter.setPen(QPen(Qt.PenStyle.NoPen))

        # ── Winner pulse glow ──────────────────────────────────────────────
        if is_winner:
            glow_r = radius * (2.1 if self._pulse else 1.5)
            glow_a = 180 if self._pulse else 90
            for r_mult, a_div in ((1.0, 1), (1.3, 3), (1.7, 6)):
                painter.setBrush(QColor(255, 210, 0, glow_a // a_div))
                painter.drawEllipse(center, glow_r * r_mult, glow_r * r_mult)

        # ── Drop shadow ────────────────────────────────────────────────────
        shadow_c = QPointF(center.x() + radius * 0.20, center.y() + radius * 0.25)
        shadow_g = QRadialGradient(shadow_c, radius * 1.1)
        shadow_g.setColorAt(0.0, QColor(0, 0, 0, 120))
        shadow_g.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(shadow_g)
        painter.drawEllipse(shadow_c, radius * 1.1, radius * 1.1)

        # ── Outer border ring ──────────────────────────────────────────────
        ring_color = QColor('#FFD700') if is_winner else QColor(255, 255, 255, 210)
        painter.setBrush(ring_color)
        painter.drawEllipse(center, radius, radius)

        # ── Piece body — glossy plastic look ──────────────────────────────
        base  = QColor(HORSE_COLORS[horse])
        inner = radius * 0.82
        body_g = QRadialGradient(
            center.x() - inner * 0.28, center.y() - inner * 0.32, inner * 1.65
        )
        body_g.setColorAt(0.00, base.lighter(180))
        body_g.setColorAt(0.30, base.lighter(120))
        body_g.setColorAt(0.65, base)
        body_g.setColorAt(1.00, base.darker(175))
        painter.setBrush(body_g)
        painter.drawEllipse(center, inner, inner)

        # ── Bounce light (bottom edge) ─────────────────────────────────────
        bounce_c = QPointF(center.x() + inner * 0.1, center.y() + inner * 0.55)
        bounce_g = QRadialGradient(bounce_c, inner * 0.6)
        bounce_g.setColorAt(0.0, QColor(255, 255, 255, 55))
        bounce_g.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(bounce_g)
        painter.drawEllipse(center, inner, inner)

        # ── Specular highlight (top-left) ──────────────────────────────────
        hi_c = QPointF(center.x() - inner * 0.33, center.y() - inner * 0.38)
        hi_g = QRadialGradient(hi_c, inner * 0.52)
        hi_g.setColorAt(0.0, QColor(255, 255, 255, 185))
        hi_g.setColorAt(0.5, QColor(255, 255, 255, 60))
        hi_g.setColorAt(1.0, QColor(255, 255, 255, 0))
        painter.setBrush(hi_g)
        painter.drawEllipse(hi_c, inner * 0.52, inner * 0.52)

        # ── Horse number ───────────────────────────────────────────────────
        font = QFont('Arial Black')
        font.setBold(True)
        font.setPointSizeF(max(6.5, inner * (0.88 if horse < 10 else 0.70)))
        painter.setFont(font)
        tr = QRectF(center.x() - inner, center.y() - inner, inner * 2, inner * 2)
        painter.setPen(QColor(0, 0, 0, 170))
        painter.drawText(tr.translated(0.7, 1.0), Qt.AlignmentFlag.AlignCenter, str(horse))
        painter.setPen(Qt.GlobalColor.white)
        painter.drawText(tr, Qt.AlignmentFlag.AlignCenter, str(horse))

        # ── Winner trophy ──────────────────────────────────────────────────
        if is_winner:
            tf = QFont('Segoe UI Emoji')
            tf.setPointSizeF(max(8.0, radius * 0.90))
            painter.setFont(tf)
            tx = center.x() + radius + 5.0
            if tx + radius * 1.5 > finish_rect.left():
                tx = center.x() - radius * 2.1
            painter.drawText(
                QRectF(tx, center.y() - radius * 0.9, radius * 1.7, radius * 1.7),
                Qt.AlignmentFlag.AlignCenter, '🏆',
            )

        painter.restore()
