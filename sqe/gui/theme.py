"""Dark, flat, modern look. One stylesheet, one palette."""
BG, PANEL, CARD, BORDER = "#0e1319", "#151c25", "#1b2430", "#2a3644"
TEXT, DIM = "#e6edf3", "#8b9bb0"
BLUE, RED, GREEN, AMBER = "#3ea6ff", "#ff5d6c", "#3ddc97", "#ffb454"

QSS = f"""
* {{ font-family: 'Segoe UI', 'Inter', 'Helvetica Neue', Arial, sans-serif; font-size: 13px; color: {TEXT}; }}
QMainWindow, QDialog, QWidget#root {{ background: {BG}; }}
QFrame#sidebar {{ background: {PANEL}; border-right: 1px solid {BORDER}; }}
QFrame#card {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 12px; }}
QLabel#title {{ font-size: 22px; font-weight: 700; }}
QLabel#h2 {{ font-size: 15px; font-weight: 600; }}
QLabel#dim, QLabel#small {{ color: {DIM}; }}
QLabel#big {{ font-size: 26px; font-weight: 700; }}
QLabel#pill {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 10px; padding: 3px 10px; color: {DIM}; }}
QPushButton {{ background: {CARD}; border: 1px solid {BORDER}; border-radius: 8px; padding: 8px 14px; }}
QPushButton:hover {{ border-color: {BLUE}; }}
QPushButton:disabled {{ color: #566275; border-color: #222c38; }}
QPushButton#nav {{ background: transparent; border: none; text-align: left; padding: 11px 16px; color: {DIM}; font-size: 14px; border-radius: 8px; }}
QPushButton#nav:hover {{ background: {CARD}; color: {TEXT}; }}
QPushButton#nav:checked {{ background: {CARD}; color: {TEXT}; border-left: 3px solid {BLUE}; }}
QPushButton#primary {{ background: {BLUE}; color: #04101c; border: none; font-weight: 700; font-size: 16px; padding: 14px 26px; }}
QPushButton#primary:hover {{ background: #62b8ff; }}
QPushButton#primary:disabled {{ background: #26425a; color: #6c8196; }}
QPushButton#danger {{ border-color: {RED}; color: {RED}; }}
QPushButton#good {{ background: {GREEN}; color: #04140c; border: none; font-weight: 700; }}
QPushButton#good:disabled {{ background: #1f4a39; color: #5f8a79; }}
QListWidget, QTableWidget, QTextEdit, QTextBrowser, QLineEdit, QComboBox, QSpinBox {{
    background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; padding: 6px; selection-background-color: #22476b; }}
QListWidget::item {{ padding: 10px; border-radius: 8px; }}
QListWidget::item:selected {{ background: #1f3a55; border: 1px solid {BLUE}; }}
QListWidget::item:hover {{ background: {CARD}; }}
QHeaderView::section {{ background: {CARD}; color: {DIM}; border: none; border-bottom: 1px solid {BORDER}; padding: 6px; font-weight: 600; }}
QTableWidget {{ gridline-color: {BORDER}; }}
QProgressBar {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 6px; text-align: center; height: 14px; color: {TEXT}; }}
QProgressBar::chunk {{ background: {BLUE}; border-radius: 5px; }}
QMenuBar {{ background: {PANEL}; }} QMenuBar::item:selected, QMenu::item:selected {{ background: #22476b; }}
QMenu {{ background: {PANEL}; border: 1px solid {BORDER}; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; }}
QTabBar::tab {{ background: {PANEL}; padding: 8px 16px; border-top-left-radius: 8px; border-top-right-radius: 8px; color: {DIM}; }}
QTabBar::tab:selected {{ background: {CARD}; color: {TEXT}; }}
QScrollBar:vertical {{ background: {PANEL}; width: 10px; }} QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
"""
