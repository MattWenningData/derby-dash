import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('Derby Dash')
    app.setOrganizationName('DerbyDash')

    window = MainWindow()
    window.showMaximized()   # fill the screen on launch
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
