from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel
from PySide6.QtCore import Qt

class PhaseBarWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 6px;
                padding: 4px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)

        self.info_lbl = QLabel("Turn: 0 | Phase: LOBBY | Active: - | Priority: -")
        self.info_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #f9e2af;")
        layout.addWidget(self.info_lbl)

        layout.addStretch()

        self.conn_lbl = QLabel("Connected")
        self.conn_lbl.setStyleSheet("font-size: 12px; color: #a6e3a1; font-weight: bold;")
        layout.addWidget(self.conn_lbl)

    def update_bar(self, turn: int, phase: str, active_player: str, priority_holder: str):
        self.info_lbl.setText(
            f"Turn: {turn} | Phase: {phase} | Active: {active_player or '-'} | Priority: {priority_holder or '-'}"
        )
