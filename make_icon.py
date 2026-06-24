"""
Generate TruckDash.ico from the fire truck emoji.
Run once during the build process:  py -3 make_icon.py
"""
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFont, QPainter, QPixmap, QColor, QImage
from PyQt6.QtCore import Qt


def make_icon(out_path: Path):
    app = QApplication.instance() or QApplication(sys.argv)

    sizes = [256, 128, 64, 48, 32, 16]
    images = []

    for sz in sizes:
        pm = QPixmap(sz, sz)
        pm.fill(QColor(0, 0, 0, 0))
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)

        # Dark red circle background
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor('#CC2200'))
        p.drawEllipse(1, 1, sz - 2, sz - 2)

        # Fire truck emoji
        f = QFont('Segoe UI Emoji')
        f.setPointSizeF(sz * 0.52)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 240))
        p.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, '🚒')
        p.end()
        images.append(pm.toImage())

    # Save as ICO (largest first)
    images[0].save(str(out_path), 'ICO')
    print(f'  Icon saved -> {out_path}')


if __name__ == '__main__':
    make_icon(Path(__file__).parent / 'TruckDash.ico')
