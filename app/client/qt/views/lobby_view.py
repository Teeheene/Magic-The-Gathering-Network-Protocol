from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QGroupBox
)
from PySide6.QtCore import Signal, Qt

class LobbyView(QWidget):
    ready_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignCenter)

        box = QGroupBox("Match Lobby")
        box.setFixedWidth(400)
        box_layout = QVBoxLayout(box)

        self.player_id_lbl = QLabel("Player ID: Assigned upon match start")
        self.player_id_lbl.setStyleSheet("font-weight: bold; font-size: 14px; color: #89b4fa;")
        box_layout.addWidget(self.player_id_lbl)

        self.status_lbl = QLabel("Waiting for players to connect...")
        self.status_lbl.setStyleSheet("color: #a6adc8; margin-top: 10px; margin-bottom: 15px;")
        box_layout.addWidget(self.status_lbl)

        self.btn_ready = QPushButton("Ready Up")
        self.btn_ready.setObjectName("btn_success")
        self.btn_ready.clicked.connect(self._on_ready_clicked)
        box_layout.addWidget(self.btn_ready)

        main_layout.addWidget(box)

    def update_state(self, player_id: str, current_state: dict):
        if player_id:
            self.player_id_lbl.setText(f"Player ID: {player_id}")
        
        phase = current_state.get("phase", "LOBBY")
        ready_cnt = current_state.get("players_ready", 0)
        waiting = current_state.get("waiting_for", "players")

        self.status_lbl.setText(f"Phase: {phase} | Ready Players: {ready_cnt} | Waiting for: {waiting}")

    def _on_ready_clicked(self):
        self.btn_ready.setEnabled(False)
        self.btn_ready.setText("Ready (Waiting...)")
        self.ready_requested.emit("default_deck")
