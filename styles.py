APP_STYLE = """
/* ── Base ──────────────────────────────────────────────────────────── */
QMainWindow, QDialog, QWidget {
    background-color: #18100A;
    color: #F0E8D0;
    font-family: "Georgia", "Palatino Linotype", serif;
}

/* Control panel gets a warm paneled look */
QWidget#control_panel_root {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #1E1408, stop:0.5 #16100A, stop:1 #1E1408);
    border-left: 1px solid #3A2A10;
}

/* ── Status bar ─────────────────────────────────────────────────────── */
QStatusBar {
    background: #0E0904;
    color: #B09050;
    font-size: 12px;
    padding: 2px 10px;
    border-top: 1px solid #2A1C08;
    font-family: "Georgia", serif;
}

/* ── Labels ──────────────────────────────────────────────────────────── */
QLabel {
    color: #F0E8D0;
    font-family: "Georgia", serif;
}
QLabel#title {
    font-size: 15px;
    font-weight: bold;
    color: #E8C84A;
    letter-spacing: 1px;
}
QLabel#status {
    font-size: 13px;
    font-weight: bold;
    color: #F5EDD8;
    padding: 6px 12px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #1C6020, stop:1 #0E3C12);
    border: 1px solid #3A8A40;
    border-bottom: 2px solid #082008;
    border-radius: 8px;
    font-family: "Georgia", serif;
}
QLabel#sum_label {
    font-size: 12px;
    font-weight: bold;
    color: #E8C84A;
    font-family: "Georgia", serif;
    padding: 3px 0;
}

/* ── Buttons ─────────────────────────────────────────────────────────── */
QPushButton {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0.00 #3C2C14,
        stop:0.40 #2C1E0C,
        stop:0.85 #221508,
        stop:1.00 #160E04);
    color: #D8C080;
    border: 1px solid #5A3A18;
    border-bottom: 2px solid #0E0804;
    border-right: 1px solid #180E04;
    border-radius: 7px;
    padding: 8px 14px;
    font-size: 12px;
    font-family: "Georgia", serif;
    letter-spacing: 0.3px;
    text-align: left;
    padding-left: 12px;
}
QPushButton:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #4C3A1C, stop:1 #2C1E0C);
    color: #F5D76E;
    border-color: #8A6030;
}
QPushButton:pressed {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #120A04, stop:1 #2C1E0C);
    border-top:    2px solid #0A0602;
    border-bottom: 1px solid #5A3A18;
    color: #C8A84B;
    padding-top: 9px;
    padding-left: 13px;
}
QPushButton:disabled {
    background: #161006;
    color: #3E2C14;
    border-color: #241808;
}

/* ── Roll Dice — large gold action button ────────────────────────────── */
QPushButton#btn_roll {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0.00 #D4A018,
        stop:0.40 #B08010,
        stop:0.85 #886008,
        stop:1.00 #604006);
    color: #FFF8E0;
    border: 1px solid #E8C840;
    border-top: 1px solid #F8E060;
    border-bottom: 3px solid #2A1C00;
    border-radius: 9px;
    font-size: 16px;
    font-weight: bold;
    padding: 11px 18px;
    text-align: center;
    letter-spacing: 0.8px;
    font-family: "Georgia", serif;
}
QPushButton#btn_roll:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #E8B828, stop:1 #A07010);
    color: #FFFFFF;
    border-color: #FFD840;
}
QPushButton#btn_roll:pressed {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #503400, stop:1 #C09010);
    border-top: 3px solid #2A1C00;
    border-bottom: 1px solid #E8C840;
    padding-top: 12px;
}
QPushButton#btn_roll:disabled {
    background: #201608;
    color: #483818;
    border-color: #2A1C08;
}

/* ── New Race — red/danger button ────────────────────────────────────── */
QPushButton#btn_reset {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #501010, stop:1 #2C0808);
    border-color: #802820;
    color: #EEC0A8;
}
QPushButton#btn_reset:hover {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #6A1818, stop:1 #3A1010);
    color: #FFD8C0;
    border-color: #A84030;
}

/* ── Inputs ──────────────────────────────────────────────────────────── */
QSpinBox, QComboBox, QLineEdit {
    background: #0C0804;
    color: #D8C880;
    border: 1px solid #3C2808;
    border-radius: 5px;
    padding: 4px 8px;
    font-size: 12px;
    font-family: "Georgia", serif;
}
QSpinBox::up-button, QSpinBox::down-button {
    background: #2C2008;
    border: none;
    width: 16px;
}
QComboBox::drop-down {
    border: none;
    background: #2C2008;
    border-radius: 0 5px 5px 0;
}
QComboBox QAbstractItemView {
    background: #0C0804;
    color: #D8C880;
    selection-background-color: #3A2810;
}

/* ── Sliders ─────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {
    background: #0C0804;
    height: 6px;
    border-radius: 3px;
    border: 1px solid #3A2010;
}
QSlider::handle:horizontal {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #EAC840, stop:1 #A08020);
    width: 17px;
    height: 17px;
    margin: -6px 0;
    border-radius: 9px;
    border: 1px solid #604010;
}
QSlider::sub-page:horizontal {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #1A5820, stop:1 #2E8A30);
    border-radius: 3px;
}

/* ── Tables & Lists ──────────────────────────────────────────────────── */
QTableWidget, QListWidget {
    background: #0C0804;
    border: 1px solid #3A2010;
    border-radius: 6px;
    gridline-color: #241408;
    color: #D8C8A0;
    font-family: "Georgia", serif;
    font-size: 11px;
    alternate-background-color: #120C06;
}
QHeaderView::section {
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #3C2C10, stop:1 #281A08);
    color: #E8C84A;
    padding: 5px 6px;
    border: none;
    border-bottom: 1px solid #5A3A18;
    font-weight: bold;
    font-size: 11px;
    font-family: "Georgia", serif;
}
QListWidget::item {
    padding: 2px 4px;
    border-bottom: 1px solid #1A1008;
}
QListWidget::item:selected {
    background: #2A1C0A;
    color: #F5D76E;
}

/* ── ScrollBar ───────────────────────────────────────────────────────── */
QScrollBar:vertical {
    background: #0C0804;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #3C2A10;
    border-radius: 4px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #5A4020; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: #0C0804;
    height: 8px;
}
QScrollBar::handle:horizontal {
    background: #3C2A10;
    border-radius: 4px;
}

/* ── GroupBox ────────────────────────────────────────────────────────── */
QGroupBox {
    border: 1px solid #3C2A10;
    border-radius: 9px;
    margin-top: 14px;
    padding: 6px 4px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #1A1008, stop:1 #120C06);
    font-size: 10px;
    font-weight: bold;
    font-family: "Georgia", serif;
    color: #C0963A;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 1px 8px;
    color: #C8A84B;
    background: #18100A;
    border: 1px solid #3C2A10;
    border-radius: 4px;
}

/* ── Message boxes ───────────────────────────────────────────────────── */
QMessageBox { background-color: #18100A; }
QMessageBox QLabel { color: #F0E8D0; font-size: 13px; }

/* ── History list ────────────────────────────────────────────────────── */
QListWidget#history_list {
    font-size: 10px;
    font-family: "Consolas", "Courier New", monospace;
    color: #C8B890;
}

/* ── Dialog boxes ────────────────────────────────────────────────────── */
QDialog { background: #18100A; }
QDialogButtonBox QPushButton { min-width: 80px; text-align: center; padding-left: 8px; }
"""
