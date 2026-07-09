from __future__ import annotations


def make_style(scale: float = 1.0) -> str:
    """Return the full app stylesheet with all font/padding sizes scaled."""

    def s(px: int) -> int:
        return max(1, int(px * scale))

    def p(px: int) -> int:
        """Padding/border — scale but stay at least 1px."""
        return max(1, int(px * scale))

    return f"""
/* ── Base ──────────────────────────────────────────────────────────── */
QMainWindow, QDialog, QWidget {{
    background-color: #18100A;
    color: #F0E8D0;
    font-family: "Georgia", "Palatino Linotype", serif;
}}

/* Control panel gets a warm paneled look */
QWidget#control_panel_root {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
        stop:0 #1E1408, stop:0.5 #16100A, stop:1 #1E1408);
    border-left: 1px solid #3A2A10;
}}

/* ── Status bar ─────────────────────────────────────────────────────── */
QStatusBar {{
    background: #0E0904;
    color: #B09050;
    font-size: {s(13)}px;
    padding: {p(2)}px {p(10)}px;
    border-top: 1px solid #2A1C08;
    font-family: "Georgia", serif;
}}

/* ── Labels ──────────────────────────────────────────────────────────── */
QLabel {{
    color: #F0E8D0;
    font-family: "Georgia", serif;
}}
QLabel#title {{
    font-size: {s(15)}px;
    font-weight: bold;
    color: #E8C84A;
    letter-spacing: 1px;
}}
QLabel#status {{
    font-size: {s(13)}px;
    font-weight: bold;
    color: #F5EDD8;
    padding: {p(6)}px {p(12)}px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #1C6020, stop:1 #0E3C12);
    border: 1px solid #3A8A40;
    border-bottom: 2px solid #082008;
    border-radius: {p(8)}px;
    font-family: "Georgia", serif;
}}
QLabel#sum_label {{
    font-size: {s(12)}px;
    font-weight: bold;
    color: #E8C84A;
    font-family: "Georgia", serif;
    padding: {p(3)}px 0;
}}

/* ── Buttons ─────────────────────────────────────────────────────────── */
QPushButton {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0.00 #3C2C14,
        stop:0.40 #2C1E0C,
        stop:0.85 #221508,
        stop:1.00 #160E04);
    color: #D8C080;
    border: 1px solid #5A3A18;
    border-bottom: 2px solid #0E0804;
    border-right: 1px solid #180E04;
    border-radius: {p(7)}px;
    padding: {p(8)}px {p(14)}px;
    font-size: {s(12)}px;
    font-family: "Georgia", serif;
    letter-spacing: 0.3px;
    text-align: left;
    padding-left: {p(12)}px;
}}
QPushButton:hover {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #4C3A1C, stop:1 #2C1E0C);
    color: #F5D76E;
    border-color: #8A6030;
}}
QPushButton:pressed {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #120A04, stop:1 #2C1E0C);
    border-top:    2px solid #0A0602;
    border-bottom: 1px solid #5A3A18;
    color: #C8A84B;
    padding-top: {p(9)}px;
    padding-left: {p(13)}px;
}}
QPushButton:disabled {{
    background: #161006;
    color: #3E2C14;
    border-color: #241808;
}}

/* ── Roll Dice — large gold action button ────────────────────────────── */
QPushButton#btn_roll {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0.00 #D4A018,
        stop:0.40 #B08010,
        stop:0.85 #886008,
        stop:1.00 #604006);
    color: #FFF8E0;
    border: 1px solid #E8C840;
    border-top: 1px solid #F8E060;
    border-bottom: 3px solid #2A1C00;
    border-radius: {p(9)}px;
    font-size: {s(16)}px;
    font-weight: bold;
    padding: {p(11)}px {p(18)}px;
    text-align: center;
    letter-spacing: 0.8px;
    font-family: "Georgia", serif;
}}
QPushButton#btn_roll:hover {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #E8B828, stop:1 #A07010);
    color: #FFFFFF;
    border-color: #FFD840;
}}
QPushButton#btn_roll:pressed {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #503400, stop:1 #C09010);
    border-top: 3px solid #2A1C00;
    border-bottom: 1px solid #E8C840;
    padding-top: {p(12)}px;
}}
QPushButton#btn_roll:disabled {{
    background: #201608;
    color: #483818;
    border-color: #2A1C08;
}}

/* ── New Race — red/danger button ────────────────────────────────────── */
QPushButton#btn_reset {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #501010, stop:1 #2C0808);
    border-color: #802820;
    color: #EEC0A8;
}}
QPushButton#btn_reset:hover {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #6A1818, stop:1 #3A1010);
    color: #FFD8C0;
    border-color: #A84030;
}}

/* ── Auto Roll button ────────────────────────────────────────────────── */
QPushButton#btn_auto {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #1A5028, stop:1 #0C2C14);
    border: 1px solid #2A7A3A;
    border-bottom: 2px solid #061408;
    color: #90E8A0;
    border-radius: {p(7)}px;
    font-weight: bold;
    font-family: "Georgia", serif;
    font-size: {s(13)}px;
    padding: {p(6)}px {p(12)}px;
}}
QPushButton#btn_auto:hover {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #246832, stop:1 #10381A);
    color: #B8FFB8;
    border-color: #40A850;
}}
QPushButton#btn_auto:checked, QPushButton#btn_auto:pressed {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #6A1818, stop:1 #3A1010);
    color: #FFB8A0;
    border-color: #A84030;
}}
QPushButton#btn_auto:disabled {{
    background: #141A14;
    color: #405040;
    border-color: #222E22;
}}

QSpinBox, QComboBox, QLineEdit {{
    background: #0C0804;
    color: #D8C880;
    border: 1px solid #3C2808;
    border-radius: {p(5)}px;
    padding: {p(4)}px {p(8)}px;
    font-size: {s(12)}px;
    font-family: "Georgia", serif;
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background: #2C2008;
    border: none;
    width: {p(16)}px;
}}
QComboBox::drop-down {{
    border: none;
    background: #2C2008;
    border-radius: 0 {p(5)}px {p(5)}px 0;
}}
QComboBox QAbstractItemView {{
    background: #0C0804;
    color: #D8C880;
    selection-background-color: #3A2810;
}}

/* ── Sliders ─────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: #0C0804;
    height: {p(6)}px;
    border-radius: {p(3)}px;
    border: 1px solid #3A2010;
}}
QSlider::handle:horizontal {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #EAC840, stop:1 #A08020);
    width: {p(17)}px;
    height: {p(17)}px;
    margin: -{p(6)}px 0;
    border-radius: {p(9)}px;
    border: 1px solid #604010;
}}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0,
        stop:0 #1A5820, stop:1 #2E8A30);
    border-radius: {p(3)}px;
}}

/* ── Tables & Lists ──────────────────────────────────────────────────── */
QTableWidget, QListWidget {{
    background: #0C0804;
    border: 1px solid #3A2010;
    border-radius: {p(6)}px;
    gridline-color: #241408;
    color: #D8C8A0;
    font-family: "Georgia", serif;
    font-size: {s(11)}px;
    alternate-background-color: #120C06;
}}
QHeaderView::section {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #3C2C10, stop:1 #281A08);
    color: #E8C84A;
    padding: {p(5)}px {p(6)}px;
    border: none;
    border-bottom: 1px solid #5A3A18;
    font-weight: bold;
    font-size: {s(11)}px;
    font-family: "Georgia", serif;
}}
QListWidget::item {{
    padding: {p(2)}px {p(4)}px;
    border-bottom: 1px solid #1A1008;
}}
QListWidget::item:selected {{
    background: #2A1C0A;
    color: #F5D76E;
}}

/* ── ScrollBar ───────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: #0C0804;
    width: {p(8)}px;
    border-radius: {p(4)}px;
}}
QScrollBar::handle:vertical {{
    background: #3C2A10;
    border-radius: {p(4)}px;
    min-height: {p(30)}px;
}}
QScrollBar::handle:vertical:hover {{ background: #5A4020; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: #0C0804;
    height: {p(8)}px;
}}
QScrollBar::handle:horizontal {{
    background: #3C2A10;
    border-radius: {p(4)}px;
}}

/* ── GroupBox ────────────────────────────────────────────────────────── */
QGroupBox {{
    border: 1px solid #3C2A10;
    border-radius: {p(9)}px;
    margin-top: {p(14)}px;
    padding: {p(6)}px {p(4)}px;
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
        stop:0 #1A1008, stop:1 #120C06);
    font-size: {s(10)}px;
    font-weight: bold;
    font-family: "Georgia", serif;
    color: #C0963A;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 1px {p(8)}px;
    color: #C8A84B;
    background: #18100A;
    border: 1px solid #3C2A10;
    border-radius: {p(4)}px;
}}

/* ── Message boxes ───────────────────────────────────────────────────── */
QMessageBox {{ background-color: #18100A; }}
QMessageBox QLabel {{ color: #F0E8D0; font-size: {s(13)}px; }}

/* ── History list ────────────────────────────────────────────────────── */
QListWidget#history_list {{
    font-size: {s(10)}px;
    font-family: "Consolas", "Courier New", monospace;
    color: #C8B890;
}}

/* ── Dialog boxes ────────────────────────────────────────────────────── */
QDialog {{ background: #18100A; }}
QDialogButtonBox QPushButton {{
    min-width: {p(80)}px;
    text-align: center;
    padding-left: {p(8)}px;
}}
"""


# Backwards-compatible alias — used by existing code that imports APP_STYLE
APP_STYLE = make_style(1.0)
