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
    QInputDialog,
    QMessageBox,
)

from app.client.pdu_dispatcher import PduDispatcher
from app.client.state import ClientState
from app.shared.card_catalog import CardCatalog
from pathlib import Path

CATALOG_PATH = Path(__file__).resolve().parents[2] / "shared" / "card_catalog.json"

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
        self.card_catalog = CardCatalog(CATALOG_PATH)

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
        header.addWidget(self.life_label)
        layout.addLayout(header)

        # Main Splitter: Game Field & Log
        splitter = QSplitter(Qt.Horizontal)
        
        # Left Panel: Game Zones
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)

        # Opponent Battlefield
        left_layout.addWidget(QLabel("Opponent Battlefield:"))
        self.opp_battlefield_list = QListWidget()
        left_layout.addWidget(self.opp_battlefield_list)

        # The Stack
        left_layout.addWidget(QLabel("The Stack (LIFO):"))
        self.stack_list = QListWidget()
        left_layout.addWidget(self.stack_list)

        # Your Battlefield
        left_layout.addWidget(QLabel("Your Battlefield:"))
        self.your_battlefield_list = QListWidget()
        left_layout.addWidget(self.your_battlefield_list)

        # Local Hand
        left_layout.addWidget(QLabel("Your Hand:"))
        self.hand_list = QListWidget()
        left_layout.addWidget(self.hand_list)

        splitter.addWidget(left_panel)

        # Right Panel: Action Log & Controls
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        right_layout.addWidget(QLabel("Game Log:"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        right_layout.addWidget(self.log_text)

        # Action Buttons
        btn_layout = QVBoxLayout()
        
        self.pass_btn = QPushButton("Pass Priority")
        self.pass_btn.clicked.connect(self.on_pass_clicked)
        btn_layout.addWidget(self.pass_btn)

        self.play_land_btn = QPushButton("Play Land")
        self.play_land_btn.clicked.connect(self.on_play_land_clicked)
        btn_layout.addWidget(self.play_land_btn)

        self.cast_spell_btn = QPushButton("Cast Spell")
        self.cast_spell_btn.clicked.connect(self.on_cast_spell_clicked)
        btn_layout.addWidget(self.cast_spell_btn)

        self.attack_btn = QPushButton("Declare Attacker")
        self.attack_btn.clicked.connect(self.on_attack_clicked)
        btn_layout.addWidget(self.attack_btn)

        self.concede_btn = QPushButton("Concede Match")
        self.concede_btn.setStyleSheet("background-color: #f38ba8; color: #11111b; font-weight: bold;")
        self.concede_btn.clicked.connect(self.on_concede_clicked)
        btn_layout.addWidget(self.concede_btn)

        right_layout.addLayout(btn_layout)
        splitter.addWidget(right_panel)

        splitter.setSizes([650, 350])
        layout.addWidget(splitter)

    def refresh_ui(self):
        phase = self.state.current_state.get("phase", "LOBBY")
        turn = self.state.current_state.get("turn", 0)
        holder = self.state.priority_holder or "None"
        self.status_label.setText(f"Phase: {phase} | Turn: {turn} | Priority: {holder}")

        opp_pid = next((p for p in self.state.life_totals if p != self.state.pid), "opponent")
        your_life = self.state.life_totals.get(self.state.pid, 20)
        opp_life = self.state.life_totals.get(opp_pid, 20)
        self.life_label.setText(f"Life Totals — You ({self.state.pid}): {your_life} | Opponent ({opp_pid}): {opp_life}")

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
        if not item:
            return
        card_id = item.text()
        base_id = card_id.split("_")[0] if "_" in card_id else card_id
        card_data = self.card_catalog.get_card_data(base_id) or {}
        mana_cost = card_data.get("mana_cost", {})

        targets = []
        text = card_data.get("text", "").casefold()
        opp_pid = next((p for p in self.state.life_totals if p != self.state.pid), "opponent")

        if "target" in text:
            # Prompt target selection
            if base_id in {"counterspell", "cancel", "mana_leak", "negate"}:
                if self.state.stack:
                    items = [f"{i.get('stack_item_id')}: {i.get('source')}" for i in self.state.stack]
                    target_str, ok = QInputDialog.getItem(self, "Select Stack Target", "Stack Item:", items, 0, False)
                    if ok and target_str:
                        targets = [target_str.split(":")[0]]
            elif base_id in {"lightning_bolt", "shock", "incinerate"}:
                choice, ok = QInputDialog.getItem(self, "Select Target", "Target:", [opp_pid, "Creature"], 0, False)
                if ok:
                    if choice == opp_pid:
                        targets = [opp_pid]
                    else:
                        opp_perms = [p.get("id") for p in self.state.battlefield.get(opp_pid, [])]
                        if opp_perms:
                            c_target, c_ok = QInputDialog.getItem(self, "Select Creature", "Creature:", opp_perms, 0, False)
                            if c_ok:
                                targets = [c_target]
            elif base_id in {"flame_slash", "unsummon", "doom_blade", "terror"}:
                opp_perms = [p.get("id") for p in self.state.battlefield.get(opp_pid, [])]
                if opp_perms:
                    c_target, c_ok = QInputDialog.getItem(self, "Select Creature Target", "Target:", opp_perms, 0, False)
                    if c_ok:
                        targets = [c_target]

        self.dispatcher.send_cast_spell(card_id, targets=targets, mana_payment=mana_cost)

    def on_attack_clicked(self):
        item = self.your_battlefield_list.currentItem()
        if item:
            cid = item.text().split(" ")[0]
            opp_pid = next((p for p in self.state.life_totals if p != self.state.pid), "player_2")
            self.dispatcher.send_declare_attackers([{"creature_id": cid, "target": opp_pid}])

    def on_concede_clicked(self):
        self.dispatcher.send_concede()
