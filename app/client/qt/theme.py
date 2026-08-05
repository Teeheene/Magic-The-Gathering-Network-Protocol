class MTGTheme:
    BG_WINDOW = "#11111b"
    BG_PANEL = "#1e1e2e"
    BG_BOARD = "#181825"
    BG_CARD = "#313244"
    BG_CARD_HOVER = "#45475a"
    BG_CARD_SELECTED = "#585b70"

    TEXT_PRIMARY = "#cdd6f4"
    TEXT_MUTED = "#a6adc8"

    ACCENT_PRIMARY = "#89b4fa"
    ACCENT_SUCCESS = "#a6e3a1"
    ACCENT_WARNING = "#f9e2af"
    ACCENT_DANGER = "#f38ba8"

    MANA_COLORS = {
        "W": "#f5e0dc",
        "U": "#89b4fa",
        "B": "#cba6f7",
        "R": "#f38ba8",
        "G": "#a6e3a1",
        "C": "#9399b2"
    }

    QSS = f"""
    QMainWindow, QDialog {{
        background-color: {BG_WINDOW};
        color: {TEXT_PRIMARY};
    }}

    QWidget {{
        color: {TEXT_PRIMARY};
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 13px;
    }}

    QGroupBox {{
        border: 1px solid #45475a;
        border-radius: 6px;
        margin-top: 10px;
        padding-top: 10px;
        font-weight: bold;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        padding: 0 5px;
        color: {ACCENT_PRIMARY};
    }}

    QLineEdit {{
        background-color: #313244;
        border: 1px solid #45475a;
        border-radius: 4px;
        padding: 6px 10px;
        color: {TEXT_PRIMARY};
    }}

    QLineEdit:focus {{
        border: 1px solid {ACCENT_PRIMARY};
    }}

    QPushButton {{
        background-color: #313244;
        border: 1px solid #45475a;
        border-radius: 5px;
        padding: 8px 16px;
        font-weight: bold;
        color: {TEXT_PRIMARY};
    }}

    QPushButton:hover {{
        background-color: #45475a;
        border-color: {ACCENT_PRIMARY};
    }}

    QPushButton:pressed {{
        background-color: #585b70;
    }}

    QPushButton:disabled {{
        background-color: #1e1e2e;
        color: #585b70;
        border-color: #313244;
    }}

    QPushButton#btn_primary {{
        background-color: {ACCENT_PRIMARY};
        color: #11111b;
        border: none;
    }}

    QPushButton#btn_primary:hover {{
        background-color: #b4befe;
    }}

    QPushButton#btn_success {{
        background-color: {ACCENT_SUCCESS};
        color: #11111b;
        border: none;
    }}

    QPushButton#btn_danger {{
        background-color: {ACCENT_DANGER};
        color: #11111b;
        border: none;
    }}

    QListWidget, QTextEdit {{
        background-color: #181825;
        border: 1px solid #313244;
        border-radius: 4px;
        color: {TEXT_PRIMARY};
    }}

    QListWidget::item:selected {{
        background-color: #45475a;
        color: {ACCENT_PRIMARY};
    }}

    QSplitter::handle {{
        background-color: #313244;
    }}
    """
