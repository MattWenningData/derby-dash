import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QFont
from PyQt6.QtCore import Qt
from main_window import MainWindow


def _make_emoji_icon(emoji: str, size: int = 64) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    f = QFont('Segoe UI Emoji')
    f.setPointSizeF(size * 0.68)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, emoji)
    p.end()
    return QIcon(pix)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Truck Dash')
    app.setOrganizationName('TruckDash')
    app.setWindowIcon(_make_emoji_icon('🚒'))

    window = MainWindow()
    window.showMaximized()   # fill the screen on launch
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
