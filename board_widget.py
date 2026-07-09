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
        self._anim_tick = 0
        self.setMinimumSize(640, 400)

        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(120)   # faster for fire/light animations
        self._pulse_timer.timeout.connect(self._on_pulse_timer)
        self._pulse_timer.start()

    def refresh(self):
        self.update()

    def _on_pulse_timer(self):
        phase  = getattr(self.game_state, 'phase', None)
        winner = getattr(self.game_state, 'winner', None)
        if phase == 'done' and winner:
            self._anim_tick += 1
            self._pulse = (self._anim_tick % 6) < 3   # ~3 Hz flip
            self.update()
        elif phase == 'racing':
            self._anim_tick += 1
            self.update()   # keep fire animated
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
        painter.drawText(rect.translated(1.5, 2.5), Qt.AlignmentFlag.AlignCenter, '🚒  TRUCK DASH')
        painter.setPen(QColor('#EAC848'))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, '🚒  TRUCK DASH')

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
            self._draw_truck_piece(painter, horse, QPointF(px, cy), piece_r, winner, finish_rect)

    def _draw_checkered_finish(self, painter: QPainter, rect: QRectF):
        import math
        painter.save()
        painter.setClipRect(rect)

        # ── Finish column background: dark green-to-amber gradient ────────
        bg = QLinearGradient(rect.topLeft(), rect.topRight())
        bg.setColorAt(0.0, QColor(10, 45, 10))
        bg.setColorAt(0.5, QColor(30, 80, 20))
        bg.setColorAt(1.0, QColor(10, 45, 10))
        painter.fillRect(rect, bg)

        # Vertical amber stripe running down the centre of the column
        stripe_w = max(4.0, rect.width() * 0.22)
        stripe_x = rect.left() + (rect.width() - stripe_w) / 2
        stripe_g = QLinearGradient(stripe_x, rect.top(), stripe_x + stripe_w, rect.top())
        stripe_g.setColorAt(0.0, QColor(200, 160, 30, 0))
        stripe_g.setColorAt(0.5, QColor(200, 160, 30, 180))
        stripe_g.setColorAt(1.0, QColor(200, 160, 30, 0))
        painter.fillRect(QRectF(stripe_x, rect.top(), stripe_w, rect.height()), stripe_g)

        # Left edge separator line
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawLine(rect.topLeft(), rect.bottomLeft())

        phase  = getattr(self.game_state, 'phase', None)
        winner = getattr(self.game_state, 'winner', None)
        t = self._anim_tick

        if phase == 'done' and winner:
            # ── Smoke: puffs originate at left edge and drift right ────────
            n_puffs = 8
            for i in range(n_puffs):
                # Spread puffs vertically along the left edge
                fy = rect.top() + (i + 0.5) * rect.height() / n_puffs
                # drift 0→1 moves puff rightward across the column
                drift   = ((t // 2 + i * 7) % 60) / 60.0
                puff_x  = rect.left() + drift * rect.width() * 0.9
                puff_wobble = math.sin((t * 0.07 + i * 1.1)) * rect.height() * 0.03
                puff_y  = fy + puff_wobble
                puff_r  = rect.height() / n_puffs * 0.7 * (0.4 + drift * 0.8)
                alpha   = int(130 * (1.0 - drift))
                grey    = 160 + (i % 3) * 20
                puff_g = QRadialGradient(puff_x, puff_y, puff_r)
                puff_g.setColorAt(0.0, QColor(grey, grey, grey, alpha))
                puff_g.setColorAt(1.0, QColor(grey, grey, grey, 0))
                painter.setBrush(puff_g)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(puff_x, puff_y), puff_r, puff_r * 0.75)
        elif phase == 'racing' or phase is None:
            # ── Flames: originate at left edge, tips point right ──────────
            n_flames = 10
            for i in range(n_flames):
                # Each flame is centred vertically at its lane position
                fy    = rect.top() + (i + 0.5) * rect.height() / n_flames
                phase_off = (i * 31 + t * 2) % 60
                # fh = how far right the flame extends (was vertical height)
                fh    = rect.width() * (0.55 + 0.45 * abs(math.sin(phase_off * 0.105)))
                # fw = the lateral (vertical) thickness of each flame tongue
                fw    = rect.height() / n_flames * 1.1
                # tip wiggles vertically (was horizontal)
                tip_y = fy + math.sin((t + i * 7) * 0.18) * fw * 0.3
                # Gradient: base at left edge → transparent at tip (right)
                fg = QLinearGradient(rect.left(), fy, rect.left() + fh, fy)
                fg.setColorAt(0.0, QColor(220, 80, 0, 200))
                fg.setColorAt(0.5, QColor(255, 160, 0, 160))
                fg.setColorAt(1.0, QColor(255, 240, 60, 0))
                flame_path = QPainterPath()
                flame_path.moveTo(rect.left(), fy - fw / 2)
                flame_path.quadTo(rect.left() + fh * 0.5, fy - fw * 0.1,
                                  rect.left() + fh,       tip_y)
                flame_path.quadTo(rect.left() + fh * 0.5, fy + fw * 0.1,
                                  rect.left(),             fy + fw / 2)
                flame_path.closeSubpath()
                painter.setBrush(fg)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawPath(flame_path)
                # Inner white-yellow core
                core_w = fh * 0.45
                cg = QLinearGradient(rect.left(), fy, rect.left() + core_w, fy)
                cg.setColorAt(0.0, QColor(255, 255, 180, 180))
                cg.setColorAt(1.0, QColor(255, 200, 50, 0))
                core_path = QPainterPath()
                core_path.moveTo(rect.left(), fy - fw * 0.22)
                core_path.quadTo(rect.left() + core_w, tip_y,
                                 rect.left(),           fy + fw * 0.22)
                core_path.closeSubpath()
                painter.setBrush(cg)
                painter.drawPath(core_path)

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

        # Give the text boxes 1.6× the column width so letters are never clipped,
        # centred on the column midpoint so they stay visually aligned.
        label_box_w = max(gate_w, finish_w) * 1.6

        # Font scales with footer height; clamp off the column widths so text
        # stays visually proportional to the columns even with the wider draw rect.
        font_pt  = min(rect.height() * 0.46,
                       gate_w   * 0.26,
                       finish_w * 0.26)
        font_pt  = max(7.0, font_pt)

        font = QFont('Georgia')
        font.setItalic(True)
        font.setBold(True)
        font.setPointSizeF(font_pt)
        painter.setFont(font)
        painter.setPen(QColor('#C8A84B'))

        start_cx   = race_rect.left()  + gate_w   / 2.0
        finish_cx  = race_rect.right() - finish_w / 2.0

        start_box  = QRectF(race_rect.left(),                    rect.top(), label_box_w, rect.height())
        finish_box = QRectF(race_rect.right() - label_box_w,     rect.top(), label_box_w, rect.height())

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

    # ── Truck piece (realistic pumper silhouette) ──────────────────────────────

    def _draw_truck_piece(self, painter: QPainter, horse: int, center: QPointF,
                          radius: float, is_winner: bool, finish_rect: QRectF):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        cx, cy = center.x(), center.y()

        # ── Dimensions ────────────────────────────────────────────────────
        # Realistic proportions: wide and low (not toy-tall)
        tw   = radius * 3.6     # total width
        th   = radius * 1.3     # body height (low-slung)
        bx   = cx - tw / 2      # left edge
        by   = cy - th / 2      # body top
        wr   = th * 0.30        # wheel radius

        # Body zones
        hood_w  = tw * 0.20     # hood in front of cab
        cab_w   = tw * 0.22     # cab width
        body_w  = tw - hood_w - cab_w   # equipment/pump body
        cab_x   = bx + body_w
        hood_x  = cab_x + cab_w

        # Cab is only slightly taller than body
        cab_h_extra = th * 0.32
        cab_top     = by - cab_h_extra
        cab_h       = th + cab_h_extra

        # ── Winner LED flash (red / white alternating like real fire truck) ─
        if is_winner:
            # _pulse alternates every ~360ms — one half red, one half white
            flash_col = QColor(255, 60, 60, 200) if self._pulse else QColor(240, 240, 255, 200)
            for r_mult, a_div in ((1.8, 1), (2.4, 3), (3.0, 7)):
                painter.setBrush(QColor(flash_col.red(), flash_col.green(),
                                        flash_col.blue(), flash_col.alpha() // a_div))
                painter.drawEllipse(center, radius * r_mult, radius * r_mult)

        # ── Drop shadow ────────────────────────────────────────────────────
        shadow = QPainterPath()
        shadow.addRoundedRect(QRectF(bx + 2, by + th * 0.6, tw, th * 0.55), 2, 2)
        painter.setBrush(QColor(0, 0, 0, 80))
        painter.drawPath(shadow)

        # ── Equipment body (rear pumper section) ──────────────────────────
        body_col  = QColor('#C01800')
        body_dark = QColor('#8A0F00')
        bg = QLinearGradient(bx, by, bx, by + th)
        bg.setColorAt(0.0, QColor('#D83020'))
        bg.setColorAt(0.35, body_col)
        bg.setColorAt(1.0, body_dark)
        painter.setBrush(bg)
        body_path = QPainterPath()
        body_path.addRect(QRectF(bx, by, body_w + 1, th))
        painter.drawPath(body_path)

        # Equipment compartment door lines (vertical panels)
        door_pen = QPen(QColor(0, 0, 0, 70), max(0.5, radius * 0.04))
        painter.setPen(door_pen)
        n_doors = max(2, int(body_w / (th * 0.9)))
        for di in range(1, n_doors):
            dx = bx + di * body_w / n_doors
            painter.drawLine(QPointF(dx, by + th * 0.08), QPointF(dx, by + th * 0.92))
        # Horizontal trim stripe
        painter.setPen(QPen(QColor(220, 200, 140, 160), max(0.8, radius * 0.06)))
        stripe_y = by + th * 0.62
        painter.drawLine(QPointF(bx, stripe_y), QPointF(bx + body_w, stripe_y))
        painter.setPen(Qt.PenStyle.NoPen)

        # ── Cab ────────────────────────────────────────────────────────────
        cab_bg = QLinearGradient(cab_x, cab_top, cab_x, cab_top + cab_h)
        cab_bg.setColorAt(0.0, QColor('#E03020'))
        cab_bg.setColorAt(0.5, body_col)
        cab_bg.setColorAt(1.0, body_dark)
        painter.setBrush(cab_bg)
        cab_path = QPainterPath()
        # Cab shape: square bottom, slightly angled top-front corner
        cab_path.moveTo(cab_x, by + th)            # bottom-left
        cab_path.lineTo(cab_x + cab_w, by + th)    # bottom-right (meets hood)
        cab_path.lineTo(cab_x + cab_w, cab_top + cab_h * 0.18)  # top-right (angled)
        cab_path.lineTo(cab_x + cab_w * 0.72, cab_top)          # roof front corner
        cab_path.lineTo(cab_x, cab_top)            # roof rear
        cab_path.closeSubpath()
        painter.drawPath(cab_path)

        # ── Windshield (angled, tinted glass) ─────────────────────────────
        ws_path = QPainterPath()
        ws_path.moveTo(cab_x + cab_w * 0.76, cab_top + cab_h * 0.20)
        ws_path.lineTo(cab_x + cab_w * 0.94, cab_top + cab_h * 0.35)
        ws_path.lineTo(cab_x + cab_w * 0.94, cab_top + cab_h * 0.72)
        ws_path.lineTo(cab_x + cab_w * 0.76, cab_top + cab_h * 0.72)
        ws_path.closeSubpath()
        painter.setBrush(QColor(160, 220, 255, 155))
        painter.drawPath(ws_path)
        # Glass reflection
        painter.setBrush(QColor(255, 255, 255, 45))
        ws_hi = QPainterPath()
        ws_hi.moveTo(cab_x + cab_w * 0.77, cab_top + cab_h * 0.22)
        ws_hi.lineTo(cab_x + cab_w * 0.88, cab_top + cab_h * 0.32)
        ws_hi.lineTo(cab_x + cab_w * 0.88, cab_top + cab_h * 0.48)
        ws_hi.lineTo(cab_x + cab_w * 0.77, cab_top + cab_h * 0.38)
        ws_hi.closeSubpath()
        painter.drawPath(ws_hi)

        # Side window (cab left)
        sw_path = QPainterPath()
        sw_path.addRoundedRect(
            QRectF(cab_x + cab_w * 0.05, cab_top + cab_h * 0.15,
                   cab_w * 0.50, cab_h * 0.46), 1, 1)
        painter.setBrush(QColor(140, 200, 255, 140))
        painter.drawPath(sw_path)

        # ── Hood ───────────────────────────────────────────────────────────
        hood_path = QPainterPath()
        hood_path.moveTo(hood_x, by)
        hood_path.lineTo(hood_x + hood_w * 0.88, by)       # hood top
        hood_path.lineTo(hood_x + hood_w, by + th * 0.32)  # nose slope
        hood_path.lineTo(hood_x + hood_w, by + th)         # bumper bottom
        hood_path.lineTo(hood_x, by + th)
        hood_path.closeSubpath()
        hood_g = QLinearGradient(hood_x, by, hood_x, by + th)
        hood_g.setColorAt(0.0, QColor('#D82818'))
        hood_g.setColorAt(1.0, body_dark)
        painter.setBrush(hood_g)
        painter.drawPath(hood_path)

        # Chrome grille/bumper strip at nose
        bumper_x = hood_x + hood_w * 0.78
        bumper_y = by + th * 0.52
        bumper_h = th * 0.48
        painter.setBrush(QLinearGradient(bumper_x, bumper_y, bumper_x + hood_w * 0.22, bumper_y))
        chrome = QLinearGradient(bumper_x, bumper_y, bumper_x, bumper_y + bumper_h)
        chrome.setColorAt(0.0, QColor(230, 230, 230))
        chrome.setColorAt(0.5, QColor(180, 180, 180))
        chrome.setColorAt(1.0, QColor(120, 120, 120))
        painter.setBrush(chrome)
        painter.drawRect(QRectF(bumper_x, bumper_y, hood_w * 0.22, bumper_h))

        # ── Wheel arches ──────────────────────────────────────────────────
        wy   = by + th - wr * 0.1
        arch_r = wr * 1.25
        for wx in (bx + body_w * 0.25, cab_x + cab_w * 0.50):
            # Arch cutout (dark)
            painter.setBrush(QColor(15, 10, 8))
            painter.drawEllipse(QPointF(wx, wy), arch_r, arch_r * 0.92)
            # Tyre
            painter.setBrush(QColor(28, 25, 22))
            painter.drawEllipse(QPointF(wx, wy), wr, wr * 0.95)
            # Rim
            rim_g = QRadialGradient(wx - wr * 0.15, wy - wr * 0.15, wr * 1.1)
            rim_g.setColorAt(0.0, QColor(210, 210, 210))
            rim_g.setColorAt(0.45, QColor(170, 170, 170))
            rim_g.setColorAt(1.0,  QColor(90,  90,  90))
            painter.setBrush(rim_g)
            painter.drawEllipse(QPointF(wx, wy), wr * 0.52, wr * 0.50)
            # Hub cap dot
            painter.setBrush(QColor(200, 200, 200))
            painter.drawEllipse(QPointF(wx, wy), wr * 0.14, wr * 0.14)

        # ── LED light bar (full-width on cab roof) ─────────────────────────
        lb_x = cab_x + cab_w * 0.05
        lb_w = cab_w * 0.82
        lb_y = cab_top - max(1.5, radius * 0.14)
        lb_h = max(1.5, radius * 0.16)
        # Bar housing
        painter.setBrush(QColor(30, 30, 30))
        painter.drawRoundedRect(QRectF(lb_x, lb_y, lb_w, lb_h * 1.6), 1, 1)
        if is_winner:
            # Flash: alternating halves (left=red when _pulse, right=white; then swap)
            left_col  = QColor(255, 50, 50, 230) if self._pulse else QColor(240, 240, 255, 230)
            right_col = QColor(240, 240, 255, 230) if self._pulse else QColor(255, 50, 50, 230)
        else:
            left_col  = QColor(255, 50, 50, 230)
            right_col = QColor(240, 240, 255, 230)
        painter.setBrush(left_col)
        painter.drawRoundedRect(QRectF(lb_x + lb_w * 0.03, lb_y + lb_h * 0.2,
                                       lb_w * 0.45, lb_h), 1, 1)
        painter.setBrush(right_col)
        painter.drawRoundedRect(QRectF(lb_x + lb_w * 0.52, lb_y + lb_h * 0.2,
                                       lb_w * 0.45, lb_h), 1, 1)

        # ── Roof-mounted ladder on body ────────────────────────────────────
        if body_w > 14:
            ly  = by - max(1.2, radius * 0.06)
            lh  = max(1.8, radius * 0.12)
            painter.setPen(QPen(QColor(180, 155, 90, 200), max(0.6, radius * 0.05)))
            painter.drawLine(QPointF(bx + 2, ly),      QPointF(bx + body_w - 2, ly))
            painter.drawLine(QPointF(bx + 2, ly + lh), QPointF(bx + body_w - 2, ly + lh))
            rungs = max(3, int(body_w / 6))
            for ri in range(rungs + 1):
                rx = bx + 2 + ri * (body_w - 4) / max(1, rungs)
                painter.drawLine(QPointF(rx, ly), QPointF(rx, ly + lh))
            painter.setPen(Qt.PenStyle.NoPen)

        # ── Truck number ───────────────────────────────────────────────────
        painter.setPen(Qt.PenStyle.NoPen)
        font = QFont('Arial Black')
        font.setBold(True)
        font.setPointSizeF(max(5.0, th * 0.50 * (0.78 if horse >= 10 else 1.0)))
        painter.setFont(font)
        nr = QRectF(bx + body_w * 0.08, by, body_w * 0.84, th * 0.58)
        painter.setPen(QColor(0, 0, 0, 130))
        painter.drawText(nr.translated(0.5, 0.8), Qt.AlignmentFlag.AlignCenter, str(horse))
        painter.setPen(QColor(255, 255, 220))
        painter.drawText(nr, Qt.AlignmentFlag.AlignCenter, str(horse))

        # ── Winner trophy ──────────────────────────────────────────────────
        if is_winner:
            tf = QFont('Segoe UI Emoji')
            tf.setPointSizeF(max(8.0, radius * 0.90))
            painter.setFont(tf)
            tx = cx + tw / 2 + 4.0
            if tx + radius * 1.5 > finish_rect.left():
                tx = cx - tw / 2 - radius * 2.0
            painter.drawText(
                QRectF(tx, cy - radius * 0.9, radius * 1.7, radius * 1.7),
                Qt.AlignmentFlag.AlignCenter, '🏆',
            )

        # ── Deck gun water arc (winner only) ──────────────────────────────
        if is_winner:
            import math
            # Gun mounts on top of body near centre
            gun_x = bx + body_w * 0.55
            gun_y = by - radius * 0.10
            # Arc target: middle of the finish column
            target_x = finish_rect.left() + finish_rect.width() * 0.3
            target_y = cy

            # Animated water droplets along a parabolic arc
            dist   = target_x - gun_x
            n_drops = 14
            t_val  = self._anim_tick
            for di in range(n_drops):
                # staggered travel progress (0→1), animated with time offset
                progress = ((di / n_drops) + (t_val * 0.04)) % 1.0
                # Parabolic arc: y = gun_y + (target_y - gun_y)*t - height*4*t*(1-t)
                arc_h = abs(dist) * 0.40
                drop_x = gun_x + progress * dist
                drop_y = (gun_y + (target_y - gun_y) * progress
                          - arc_h * 4 * progress * (1 - progress))
                # Fade in/out and size vary by position
                alpha  = int(200 * math.sin(progress * math.pi))
                r_drop = max(1.5, radius * 0.08 * (0.5 + math.sin(progress * math.pi) * 0.7))
                # Water colour: bright cyan/blue
                dg = QRadialGradient(drop_x, drop_y, r_drop * 2)
                dg.setColorAt(0.0, QColor(140, 220, 255, alpha))
                dg.setColorAt(0.6, QColor(60, 160, 255, alpha // 2))
                dg.setColorAt(1.0, QColor(30, 100, 200, 0))
                painter.setBrush(dg)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(QPointF(drop_x, drop_y), r_drop * 2, r_drop * 2)

            # Draw the gun barrel itself
            painter.setPen(QPen(QColor(60, 60, 60), max(1.0, radius * 0.10)))
            painter.drawLine(QPointF(gun_x, gun_y),
                             QPointF(gun_x + dist * 0.12, gun_y - radius * 0.35))
            painter.setPen(Qt.PenStyle.NoPen)

        painter.restore()




