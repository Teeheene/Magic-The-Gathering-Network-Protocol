from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QTextEdit

class EventLogWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("Game Event Log")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #89b4fa;")
        layout.addWidget(title)

        self.text_edit = QTextEdit()
        self.text_edit.setReadOnly(True)
        layout.addWidget(self.text_edit)

    def log_event(self, message: str):
        self.text_edit.append(message)
