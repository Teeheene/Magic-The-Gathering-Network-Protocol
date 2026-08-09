from typing import Any, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app.client.pdu_dispatcher import PduDispatcher
from app.client.state import ClientState


class MainWindow(QMainWindow):
    """
    PySide6 Graphical Client Window for MTGNP 1.0.
    Pure view layer bound to ClientState and PduDispatcher.
    """

    state_updated_signal = Signal()

    def __init__(self, state: ClientState, dispatcher: PduDispatcher, parent=None):
        super().__init__(parent)
        self.state = state
        self.dispatcher = dispatcher

        self.setWindowTitle(f"MTGNP 1.0 Client — Player: {self.state.pid}")
        self.resize(1024, 768)

        self._init_ui()
        self.state_updated_signal.connect(self.refresh_ui)

    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)

        # Header Info Bar
        header = QHBoxLayout()
        self.status_label = QLabel("Phase: LOBBY | Turn: 0")
        self.status_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #89b4fa;")
        self.life_label = QLabel("Life Totals — You: 20 | Opponent: 20")
        self.life_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #a6e3a1;")
        header.addWidget(self.status_label)
        header.addStretch()
        header.addWidget(self.life_label)
        layout.addLayout(header)

        # Splitter: Battlefield + Hand on Left, Log + Stack on Right
        splitter = QSplitter(Qt.Horizontal)

        left_container = QWidget()
        left_layout = QVBoxLayout(left_container)

        left_layout.addWidget(QLabel("Opponent Battlefield:"))
        self.opp_battlefield_list = QListWidget()
        left_layout.addWidget(self.opp_battlefield_list)

        left_layout.addWidget(QLabel("Your Battlefield:"))
        self.your_battlefield_list = QListWidget()
        left_layout.addWidget(self.your_battlefield_list)

        left_layout.addWidget(QLabel("Your Hand:"))
        self.hand_list = QListWidget()
        left_layout.addWidget(self.hand_list)

        splitter.addWidget(left_container)

        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)

        right_layout.addWidget(QLabel("Stack:"))
        self.stack_list = QListWidget()
        right_layout.addWidget(self.stack_list)

        right_layout.addWidget(QLabel("Game Log:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        right_layout.addWidget(self.log_text)

        splitter.addWidget(right_container)
        layout.addWidget(splitter)

        # Action Buttons Toolbar
        actions = QHBoxLayout()
        self.pass_btn = QPushButton("Pass Priority")
        self.play_land_btn = QPushButton("Play Land")
        self.cast_spell_btn = QPushButton("Cast Spell")
        self.attack_btn = QPushButton("Declare Attackers")
        self.concede_btn = QPushButton("Concede")

        self.pass_btn.clicked.connect(self.on_pass_clicked)
        self.play_land_btn.clicked.connect(self.on_play_land_clicked)
        self.cast_spell_btn.clicked.connect(self.on_cast_spell_clicked)
        self.attack_btn.clicked.connect(self.on_attack_clicked)
        self.concede_btn.clicked.connect(self.on_concede_clicked)

        actions.addWidget(self.pass_btn)
        actions.addWidget(self.play_land_btn)
        actions.addWidget(self.cast_spell_btn)
        actions.addWidget(self.attack_btn)
        actions.addWidget(self.concede_btn)
        layout.addLayout(actions)

    def refresh_ui(self):
        self.status_label.setText(
            f"Phase: {self.state.phase} | Turn: {self.state.turn} | Active: {self.state.active_player or 'N/A'}"
        )
        my_life = self.state.life_totals.get(self.state.pid, 20)
        opp_pid = next((p for p in self.state.life_totals if p != self.state.pid), "Opponent")
        opp_life = self.state.life_totals.get(opp_pid, 20)
        self.life_label.setText(f"You ({self.state.pid}): {my_life} HP | Opponent ({opp_pid}): {opp_life} HP")

        # Refresh hand
        self.hand_list.clear()
        for card_id in self.state.local_hand:
            self.hand_list.addItem(card_id)

        # Refresh battlefields
        self.your_battlefield_list.clear()
        for perm in self.state.battlefield.get(self.state.pid, []):
            cid = perm.get("id", str(perm))
            tapped = " [Tapped]" if perm.get("tapped") else ""
            self.your_battlefield_list.addItem(f"{cid}{tapped}")

        self.opp_battlefield_list.clear()
        for perm in self.state.battlefield.get(opp_pid, []):
            cid = perm.get("id", str(perm))
            tapped = " [Tapped]" if perm.get("tapped") else ""
            self.opp_battlefield_list.addItem(f"{cid}{tapped}")

        # Refresh stack
        self.stack_list.clear()
        for idx, item in enumerate(self.state.stack):
            src = item.get("source", "Spell")
            ctrl = item.get("controller", "")
            self.stack_list.addItem(f"[{idx}] {src} (Controller: {ctrl})")

    def on_pass_clicked(self):
        self.dispatcher.send_priority_pass()

    def on_play_land_clicked(self):
        item = self.hand_list.currentItem()
        if item:
            self.dispatcher.send_play_land(item.text())

    def on_cast_spell_clicked(self):
        item = self.hand_list.currentItem()
        if item:
            self.dispatcher.send_cast_spell(item.text(), targets=[], mana_payment={})

    def on_attack_clicked(self):
        item = self.your_battlefield_list.currentItem()
        if item:
            cid = item.text().split(" ")[0]
            opp_pid = next((p for p in self.state.life_totals if p != self.state.pid), "player_2")
            self.dispatcher.send_declare_attackers([{"creature_id": cid, "target": opp_pid}])

    def on_concede_clicked(self):
        self.dispatcher.send_concede()
