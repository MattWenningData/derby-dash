from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QHBoxLayout, QMainWindow, QMessageBox, QStatusBar, QVBoxLayout, QLabel, QWidget,
)

from board_widget   import BoardWidget
from control_panel  import ControlPanel, CompactRacePanel, DiceWidget
from game_state     import GameState
from styles         import APP_STYLE




class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Truck Dash')
        self.setMinimumSize(800, 480)
        self.game = GameState()

        self._admin_dialog  = None
        self._webcam_dialog = None

        # Auto-roll state
        self._auto_rolling  = False
        self._roll_delay_ms = 1200
        self._auto_timer    = QTimer(self)
        self._auto_timer.setSingleShot(True)
        self._auto_timer.timeout.connect(self._auto_roll_step)

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
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Main row: board + compact panel ───────────────────────────────
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Board fills most space
        self.board = BoardWidget(self.game)
        layout.addWidget(self.board, stretch=5)

        # Slim right panel: dice result + standings only
        self.compact_panel = CompactRacePanel(self.game)
        self.compact_panel.controls_requested.connect(self._show_controls)
        layout.addWidget(self.compact_panel, stretch=1)

        outer.addWidget(row, stretch=1)

        # ── Winner banner (hidden until a race ends) ───────────────────────
        self._winner_banner = QLabel('')
        self._winner_banner.setObjectName('winner_banner')
        self._winner_banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._winner_banner.setWordWrap(True)
        self._winner_banner.setFixedHeight(54)
        self._winner_banner.hide()
        outer.addWidget(self._winner_banner)

        # ── Full control window — lives on the second screen ──────────────
        self.panel = ControlPanel(self.game)
        self.panel.roll_requested.connect(self._do_roll)
        self.panel.auto_roll_requested.connect(self._toggle_auto_roll)
        self.panel.reset_requested.connect(self._do_reset)
        self.panel.admin_requested.connect(self._open_admin)
        self.panel.webcam_requested.connect(self._open_webcam)
        self.panel.history_requested.connect(self._open_history)
        self.panel.speed_changed.connect(self._set_roll_speed)
        self.panel.counter_reset.connect(self.compact_panel.race_history_panel.refresh)
        self.panel.show_on_second_screen()

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage('Welcome to Truck Dash!  Click Roll Dice to begin.   [ F11 = full screen ]')

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showMaximized()
        else:
            self.showFullScreen()

    def _set_roll_speed(self, ms: int):
        self._roll_delay_ms = ms

    def _show_controls(self):
        """Raise (or re-show) the control window."""
        self.panel.show()
        self.panel.raise_()
        self.panel.activateWindow()

    # ── Auto Roll ──────────────────────────────────────────────────────────

    def _toggle_auto_roll(self):
        if self._auto_rolling:
            self._stop_auto_roll()
        elif self.game.phase == 'racing':
            self._start_auto_roll()

    def _start_auto_roll(self):
        self._auto_rolling = True
        self._refresh()
        self._auto_roll_step()   # fire the first roll immediately

    def _stop_auto_roll(self):
        self._auto_rolling = False
        self._auto_timer.stop()
        self.compact_panel.stop_animation()
        self._refresh()
        self.status_bar.showMessage('Auto Roll stopped.')

    def _auto_roll_step(self):
        if not self._auto_rolling or self.game.phase != 'racing':
            self._stop_auto_roll()
            return
        # Animate dice first; result is applied when animation finishes
        self.compact_panel.show_roll_animation(on_complete=self._apply_auto_roll)
        self.panel.show_roll_animation()

    def _apply_auto_roll(self):
        if not self._auto_rolling:
            return
        if self.game.phase != 'racing':
            self._stop_auto_roll()
            return
        d1, d2 = self.game.roll_dice()
        horse, won = self.game.apply_roll(d1, d2)
        self.status_bar.showMessage(
            f'Auto Roll #{len(self.game.roll_log)}:  {d1} + {d2} = {d1+d2}  →  Truck #{horse} advances!'
        )
        self._refresh()
        if won:
            self._auto_rolling = False
            QTimer.singleShot(1200, lambda: self._announce_winner(horse))
        else:
            self._auto_timer.start(self._roll_delay_ms)

    # ── Game actions ───────────────────────────────────────────────────────

    def _do_roll(self):
        if self.game.phase != 'racing':
            return
        self.panel.btn_roll.setEnabled(False)
        self.panel.show_roll_animation()
        self.compact_panel.show_roll_animation()
        QTimer.singleShot(480, self._apply_roll)

    def _apply_roll(self):
        d1, d2 = self.game.roll_dice()
        horse, won = self.game.apply_roll(d1, d2)
        self.status_bar.showMessage(
            f'Rolled  {d1} + {d2} = {d1+d2}  →  Truck #{horse} advances!'
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
            f'Webcam roll:  {d1} + {d2} = {d1+d2}  →  Truck #{horse} advances!'
        )
        self._refresh()
        if won:
            self._announce_winner(horse)

    def _do_reset(self):
        if self._auto_rolling:
            self._stop_auto_roll()
        reply = QMessageBox.question(
            self, 'New Race', 'Start a new race?  All positions will be reset.',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.game.reset()
            self._winner_banner.hide()
            self.status_bar.showMessage('New race!  Click Roll Dice to begin.')
            self._refresh()

    # ── Winner announcement ────────────────────────────────────────────────

    def _announce_winner(self, horse: int):
        from race_history import save_race
        try:
            save_race(self.game)
        except Exception:
            pass

        banner_text = (
            f'🏆  TRUCK #{horse} WINS!     '
            f'Total rolls: {len(self.game.roll_log)}'
        )
        self._winner_banner.setText(banner_text)
        self._winner_banner.setStyleSheet(
            'background: qlineargradient(x1:0,y1:0,x2:1,y2:0,'
            'stop:0 #8B4A00, stop:0.3 #C07800, stop:0.5 #E8C030, '
            'stop:0.7 #C07800, stop:1 #8B4A00);'
            'color: #1A0A00; font-size: 18px; font-weight: bold;'
            'font-family: Georgia, serif;'
            'border-top: 3px solid #FFD700; padding: 6px 16px;'
        )
        self._winner_banner.show()
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
        self.panel.refresh(auto_rolling=self._auto_rolling)
        self.compact_panel.refresh()
        self.board.refresh()
