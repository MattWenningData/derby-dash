from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout, QMainWindow, QMessageBox, QStatusBar, QWidget,
)

from board_widget   import BoardWidget
from control_panel  import ControlPanel
from game_state     import GameState
from styles         import APP_STYLE


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Derby Dash')
        self.setMinimumSize(800, 480)
        self.game = GameState()

        self._admin_dialog  = None
        self._webcam_dialog = None

        self._build_ui()
        self.setStyleSheet(APP_STYLE)
        self._refresh()

        # F11 toggles full-screen (handy for TV/fair use)
        fs_shortcut = QShortcut(QKeySequence('F11'), self)
        fs_shortcut.activated.connect(self._toggle_fullscreen)

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Board fills all available space; panel takes ~20 %
        self.board = BoardWidget(self.game)
        layout.addWidget(self.board, stretch=5)

        self.panel = ControlPanel(self.game)
        self.panel.roll_requested.connect(self._do_roll)
        self.panel.reset_requested.connect(self._do_reset)
        self.panel.admin_requested.connect(self._open_admin)
        self.panel.webcam_requested.connect(self._open_webcam)
        self.panel.history_requested.connect(self._open_history)
        layout.addWidget(self.panel, stretch=1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage('Welcome to Derby Dash!  Click Roll Dice to begin.   [ F11 = full screen ]')

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    # ── Game actions ───────────────────────────────────────────────────────

    def _do_roll(self):
        if self.game.phase != 'racing':
            return
        self.panel.btn_roll.setEnabled(False)
        self.panel.show_roll_animation()
        QTimer.singleShot(480, self._apply_roll)

    def _apply_roll(self):
        d1, d2 = self.game.roll_dice()
        horse, won = self.game.apply_roll(d1, d2)
        self.status_bar.showMessage(
            f'Rolled  {d1} + {d2} = {d1+d2}  →  Horse #{horse} advances!'
        )
        self._refresh()
        if won:
            self._announce_winner(horse)
        else:
            self.panel.btn_roll.setEnabled(True)

    def _apply_webcam_roll(self, d1: int, d2: int):
        if self.game.phase != 'racing':
            return
        horse, won = self.game.apply_roll(d1, d2)
        self.status_bar.showMessage(
            f'Webcam roll:  {d1} + {d2} = {d1+d2}  →  Horse #{horse} advances!'
        )
        self._refresh()
        if won:
            self._announce_winner(horse)

    def _do_reset(self):
        reply = QMessageBox.question(
            self, 'New Race', 'Start a new race?  All positions will be reset.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.game.reset()
            self.status_bar.showMessage('New race!  Click Roll Dice to begin.')
            self._refresh()

    # ── Winner announcement ────────────────────────────────────────────────

    def _announce_winner(self, horse: int):
        from constants import COMBINATIONS
        from race_history import save_race
        combos = COMBINATIONS[horse]
        odds   = 36 // combos

        # Save to CSV before showing popup
        try:
            csv_path = save_race(self.game)
            saved_msg = f'\n\nRace saved to:\n{csv_path}'
        except Exception as exc:
            saved_msg = f'\n\n(Could not save history: {exc})'

        msg = (
            f'🏆  Horse #{horse} wins the race!\n\n'
            f'Dice combinations: {combos} out of 36\n'
            f'Approximate odds:  {odds}:1\n\n'
            f'Total rolls: {len(self.game.roll_log)}'
            f'{saved_msg}'
        )
        QMessageBox.information(self, '🏁  Race Over!', msg)
        self._refresh()

    # ── Dialogs ────────────────────────────────────────────────────────────

    def _open_history(self):
        from history_dialog import HistoryDialog
        dlg = HistoryDialog(self)
        dlg.exec()

    def _open_admin(self):
        from admin_dialog import AdminDialog
        if self._admin_dialog is None or not self._admin_dialog.isVisible():
            self._admin_dialog = AdminDialog(self.game, self)
            self._admin_dialog.positions_changed.connect(self._on_admin_change)
        self._admin_dialog.sync_from_state()
        self._admin_dialog.show()
        self._admin_dialog.raise_()

    def _on_admin_change(self):
        self._refresh()
        if self.game.phase == 'done' and self.game.winner:
            self._announce_winner(self.game.winner)

    def _open_webcam(self):
        if self.game.phase != 'racing':
            QMessageBox.information(
                self, 'Webcam Dice',
                'The race must be in progress to use webcam dice.'
            )
            return
        from webcam_dialog import WebcamDialog
        if self._webcam_dialog is None or not self._webcam_dialog.isVisible():
            self._webcam_dialog = WebcamDialog(self)
            self._webcam_dialog.dice_detected.connect(self._apply_webcam_roll)
        self._webcam_dialog.show()
        self._webcam_dialog.raise_()

    # ── Refresh ────────────────────────────────────────────────────────────

    def _refresh(self):
        self.panel.refresh()
        self.board.refresh()
