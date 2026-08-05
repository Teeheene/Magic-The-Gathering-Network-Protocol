from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QGroupBox
)
from PySide6.QtCore import Signal, Qt

class GameOverView(QWidget):
    return_lobby_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignCenter)

        box = QGroupBox("Match Result - Game Over")
        box.setFixedWidth(400)
        box_layout = QVBoxLayout(box)

        self.winner_lbl = QLabel("Winner: -")
        self.winner_lbl.setStyleSheet("font-size: 16px; font-weight: bold; color: #a6e3a1;")
        box_layout.addWidget(self.winner_lbl)

        self.reason_lbl = QLabel("Reason: -")
        self.reason_lbl.setStyleSheet("color: #a6adc8; margin-bottom: 15px;")
        box_layout.addWidget(self.reason_lbl)

        self.btn_lobby = QPushButton("Return to Lobby")
        self.btn_lobby.setObjectName("btn_primary")
        self.btn_lobby.clicked.connect(self._on_lobby_clicked)
        box_layout.addWidget(self.btn_lobby)

        main_layout.addWidget(box)

    def set_result(self, winner_id: str, reason: str, local_player_id: str = ""):
        if local_player_id and winner_id == local_player_id:
            self.winner_lbl.setText(f"VICTORY! Winner: {winner_id}")
            self.winner_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #a6e3a1;")
        elif winner_id:
            self.winner_lbl.setText(f"DEFEAT! Winner: {winner_id}")
            self.winner_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #f38ba8;")
        else:
            self.winner_lbl.setText("Game Over")

        self.reason_lbl.setText(f"Reason: {reason}")

    def _on_lobby_clicked(self):
        self.return_lobby_requested.emit()
