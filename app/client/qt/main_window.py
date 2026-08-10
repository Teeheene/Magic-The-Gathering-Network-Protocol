from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QListWidget,
    QMainWindow, QPushButton, QScrollArea, QStackedWidget, QTextEdit,
    QLineEdit, QInputDialog, QMessageBox, QVBoxLayout, QWidget,
)

from app.client.qt.dialogs import CardChoiceDialog, MulliganDialog, TriggerChoiceDialog
from app.client.qt.presenter import GamePresenter
from app.client.pdu_dispatcher import PduDispatcher
from app.shared.card_catalog import CardCatalog

CATALOG_PATH = Path(__file__).resolve().parents[2] / "shared" / "card_catalog.json"


class MainWindow(QMainWindow):
    """Thread-safe Qt shell: dispatcher updates ClientState, then emits a refresh signal."""

    state_updated_signal = Signal()

    def __init__(self, state, dispatcher: PduDispatcher, parent=None):
        super().__init__(parent)
        self.state = state
        self.dispatcher = dispatcher
        self.catalog = CardCatalog(CATALOG_PATH)
        self.presenter = GamePresenter(state, self.catalog)
        self._choice_dialog_open = False
        self._selected_attackers = []
        self.setWindowTitle(f"MTGNP 1.0 Client — Player: {state.pid}")
        self.resize(1366, 820)
        self._build_ui()
        self.state_updated_signal.connect(self.refresh_ui)
        self.refresh_ui()

    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        self.status_label = QLabel("Phase: LOBBY | Turn: 0")
        self.life_label = QLabel("Life Totals â€” You: 20 | Opponent: 20")
        self.status_label.setObjectName("Status")
        self.life_label.setObjectName("Life")
        outer.addWidget(self.status_label)
        outer.addWidget(self.life_label)
        self.pages = QStackedWidget()
        outer.addWidget(self.pages, 1)
        self._build_connection_page()
        self._build_lobby_page()
        self._build_mulligan_page()
        self._build_game_page()
        self.setStyleSheet("""
            QWidget { background:#10161d; color:#edf2f7; font-size:13px; }
            QGroupBox { border:1px solid #354352; border-radius:8px; margin-top:8px; padding:10px; }
            QGroupBox::title { subcontrol-origin:margin; left:10px; color:#e4b56a; }
            QPushButton { background:#273646; border:1px solid #506276; border-radius:6px; padding:9px 14px; }
            QPushButton:hover { background:#35506a; }
            QPushButton#Primary { background:#b66a27; border-color:#e4a45c; font-weight:700; }
            QPushButton#Danger { background:#79343d; }
            QListWidget, QTextEdit, QLineEdit, QComboBox { background:#18232d; border:1px solid #354352; border-radius:5px; padding:5px; }
            QLabel#Status { color:#e4b56a; font-size:16px; font-weight:700; }
            QLabel#Life { color:#9fd6a6; font-weight:700; }
        """)

    def _build_connection_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        box = QGroupBox("1. LAUNCH / CONNECT"); form = QFormLayout(box)
        self.host_edit = QLineEdit("127.0.0.1"); self.port_edit = QLineEdit("5000")
        self.name_edit = QLineEdit(self.state.pid)
        self.deck_combo = QComboBox()
        self.deck_combo.addItem("Forest's Might (Green)")
        form.addRow("Server host", self.host_edit); form.addRow("Port", self.port_edit)
        form.addRow("Player name", self.name_edit); form.addRow("Deck", self.deck_combo)
        layout.addWidget(box)
        self.connect_btn = QPushButton("CONNECT"); self.connect_btn.setObjectName("Primary")
        self.connect_btn.clicked.connect(self.connect_to_server); layout.addWidget(self.connect_btn)
        self.connection_error = QLabel(""); layout.addWidget(self.connection_error); layout.addStretch()
        self.pages.addWidget(page)

    def _build_lobby_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        self.lobby_title = QLabel("2. LOBBY"); layout.addWidget(self.lobby_title)
        self.lobby_status = QLabel("Waiting for opponent..."); layout.addWidget(self.lobby_status)
        row = QHBoxLayout()
        self.ready_btn = QPushButton("READY"); self.ready_btn.setObjectName("Primary"); self.ready_btn.clicked.connect(self.send_ready)
        self.leave_btn = QPushButton("LEAVE LOBBY"); self.leave_btn.setObjectName("Danger"); self.leave_btn.clicked.connect(self.close_connection)
        row.addWidget(self.ready_btn); row.addWidget(self.leave_btn); layout.addLayout(row); layout.addStretch()
        self.pages.addWidget(page)

    def _build_mulligan_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        layout.addWidget(QLabel("3. MULLIGAN DECISION"))
        self.mulligan_hand = QListWidget(); self.mulligan_hand.setSelectionMode(QListWidget.MultiSelection); layout.addWidget(self.mulligan_hand)
        row = QHBoxLayout(); self.keep_btn = QPushButton("KEEP"); self.keep_btn.setObjectName("Primary"); self.keep_btn.clicked.connect(lambda: self.dispatcher.send_mulligan_choice(True))
        self.mull_btn = QPushButton("MULLIGAN"); self.mull_btn.setObjectName("Danger"); self.mull_btn.clicked.connect(lambda: self.dispatcher.send_mulligan_choice(False))
        row.addWidget(self.keep_btn); row.addWidget(self.mull_btn); layout.addLayout(row)
        self.pages.addWidget(page)

    def _build_game_page(self):
        page = QWidget(); layout = QVBoxLayout(page)
        board = QHBoxLayout(); left = QVBoxLayout(); right = QVBoxLayout()
        self.opponent_info = QLabel("Opponent")
        self.opp_battlefield_list = QListWidget(); self.your_battlefield_list = QListWidget(); self.hand_list = QListWidget()
        self.stack_list = QListWidget(); self.exile_list = QListWidget(); self.log_text = QTextEdit(); self.log_text.setReadOnly(True)
        for title, widget in (("Opponent Battlefield", self.opp_battlefield_list), ("Your Battlefield", self.your_battlefield_list), ("Your Hand", self.hand_list)):
            left.addWidget(QLabel(title)); left.addWidget(widget, 1)
        right.addWidget(QLabel("The Stack (Top)")); right.addWidget(self.stack_list, 2)
        right.addWidget(QLabel("Your Exile / Suspended Cards")); right.addWidget(self.exile_list, 1)
        right.addWidget(QLabel("Status / Errors")); right.addWidget(self.log_text, 1)
        board.addLayout(left, 3); board.addLayout(right, 2); layout.addLayout(board, 1)
        actions = QHBoxLayout()
        self.pass_btn = QPushButton("PASS PRIORITY"); self.pass_btn.clicked.connect(self.on_pass_clicked)
        self.play_land_btn = QPushButton("PLAY LAND"); self.play_land_btn.clicked.connect(self.on_play_land_clicked)
        self.cast_spell_btn = QPushButton("CAST SPELL"); self.cast_spell_btn.setObjectName("Primary"); self.cast_spell_btn.clicked.connect(self.on_cast_spell_clicked)
        self.activate_btn = QPushButton("ACTIVATE"); self.activate_btn.clicked.connect(self.on_activate_clicked)
        self.attack_btn = QPushButton("CONFIRM ATTACKERS"); self.attack_btn.clicked.connect(self.on_attack_clicked)
        self.suspend_btn = QPushButton("SUSPEND"); self.suspend_btn.clicked.connect(self.on_suspend_clicked)
        self.concede_btn = QPushButton("CONCEDE"); self.concede_btn.setObjectName("Danger"); self.concede_btn.clicked.connect(lambda: self.dispatcher.send_concede())
        for button in (self.pass_btn, self.play_land_btn, self.cast_spell_btn, self.activate_btn, self.attack_btn, self.suspend_btn, self.concede_btn): actions.addWidget(button)
        layout.addLayout(actions); self.pages.addWidget(page)

    def connect_to_server(self):
        try:
            self.state.pid = self.name_edit.text().strip() or self.state.pid
            connection = self.dispatcher.connection
            connection.host = self.host_edit.text().strip(); connection.port = int(self.port_edit.text())
            connection.connect(); connection.start_heartbeat(self.dispatcher)
            self.send_ready()
        except (OSError, ValueError) as error:
            self.connection_error.setText(f"Connection failed: {error}")

    def send_ready(self):
        self.dispatcher.send_player_ready()

    def close_connection(self):
        self.dispatcher.connection.close()
        self.state.reset_for_lobby(); self.refresh_ui()

    def refresh_ui(self):
        phase = self.state.phase or self.state.current_state.get("phase", "LOBBY")
        turn = self.state.turn or self.state.current_state.get("turn", 0)
        holder = self.state.priority_holder or "None"
        self.status_label.setText(f"Phase: {phase} | Turn: {turn} | Priority: {holder}")
        opponent = self.presenter.opponent_id() or "Opponent"
        self.life_label.setText(f"Life Totals â€” You ({self.state.pid}): {self.state.life_totals.get(self.state.pid, 20)} | Opponent ({opponent}): {self.state.life_totals.get(opponent, 20)}")
        if phase == "LOBBY": self.pages.setCurrentWidget(self.pages.widget(0))
        elif phase == "MULLIGAN": self.pages.setCurrentWidget(self.pages.widget(2))
        elif phase == "GAME_OVER": self.pages.setCurrentWidget(self.pages.widget(3))
        elif phase in {"GAME_SETUP", "LOBBY"}: self.pages.setCurrentWidget(self.pages.widget(1))
        else: self.pages.setCurrentWidget(self.pages.widget(3))
        self._refresh_lists(opponent)
        self._refresh_actions(phase)
        self._refresh_choice()
        if getattr(self.state, "last_error", None):
            error = self.state.last_error
            self.log_text.setPlainText(f"{error.get('code', 'ERROR')}: {error.get('message', '')}")

    def _refresh_lists(self, opponent):
        self.hand_list.clear(); self.mulligan_hand.clear()
        for card_id in self.state.local_hand:
            self.hand_list.addItem(card_id); self.mulligan_hand.addItem(card_id)
        self.your_battlefield_list.clear(); self.opp_battlefield_list.clear()
        for card in self.state.battlefield.get(self.state.pid, []): self.your_battlefield_list.addItem(card.get("id", str(card)))
        for card in self.state.battlefield.get(opponent, []): self.opp_battlefield_list.addItem(card.get("id", str(card)))
        self.stack_list.clear()
        for item in self.state.stack: self.stack_list.addItem(f"{item.get('source', 'Ability')} — {item.get('controller', '')}")
        self.exile_list.clear()
        for card_id in self.state.exile.get(self.state.pid, []): self.exile_list.addItem(card_id)

    def _refresh_actions(self, phase):
        usable = self.state.priority_holder == self.state.pid and self.state.priority_seq_num is not None
        self.pass_btn.setEnabled(usable or phase == "LOBBY"); self.play_land_btn.setEnabled(usable and phase in {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"})
        self.cast_spell_btn.setEnabled(usable); self.activate_btn.setEnabled(usable)
        self.attack_btn.setEnabled(phase == "DECLARE_ATTACKERS" and self.state.active_player == self.state.pid)
        self.suspend_btn.setEnabled(usable and phase in {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"})
        self.concede_btn.setEnabled(True)

    def _refresh_choice(self):
        request = self.state.pending_card_choice
        if request is None or self._choice_dialog_open: return
        self._choice_dialog_open = True
        dialog = CardChoiceDialog(request, self)
        if dialog.exec(): self.dispatcher.send_card_choice_response(**dialog.result)
        self._choice_dialog_open = False

    def on_pass_clicked(self): self.dispatcher.send_priority_pass()

    def on_play_land_clicked(self):
        item = self.hand_list.currentItem()
        if item: self.dispatcher.send_play_land(item.text())

    def _select_target(self, card_id):
        data = self.catalog.get_card_data(card_id) or {}; base = CardCatalog.base_card_id(card_id)
        opponent = self.presenter.opponent_id()
        if base in {"counterspell", "cancel", "mana_leak", "negate"}:
            options = [str(item.get("stack_item_id")) for item in self.state.stack if item.get("item_type") == "SPELL"]
        elif base in {"lava_spike", "ponder", "mind_rot"}:
            options = [opponent] if opponent else []
        else:
            options = [opponent] if opponent else []
            options += [p.get("id") for pid in self.state.battlefield for p in self.state.battlefield.get(pid, []) if "creature" in (self.catalog.get_card_data(p.get("id", "")) or {}).get("card_type", "").casefold()]
        choice, ok = QInputDialog.getItem(self, "Select target", "Target:", options, 0, False)
        return [choice] if ok and choice else []

    def on_cast_spell_clicked(self):
        item = self.hand_list.currentItem()
        if not item: return
        card_id = item.text(); data = self.catalog.get_card_data(card_id) or {}; base = CardCatalog.base_card_id(card_id)
        targets = self._select_target(card_id) if "target" in data.get("text", "").casefold() else []
        mode = None
        if base == "healing_salve":
            mode, ok = QInputDialog.getItem(self, "Healing Salve", "Mode:", ["GAIN_LIFE", "PREVENT_DAMAGE"], 0, False)
            if not ok: return
        self.dispatcher.send_cast_spell(card_id, targets=targets, mana_payment={"X" if key == "Generic" else key: value for key, value in data.get("mana_cost", {}).items() if value}, mode=mode)

    def on_activate_clicked(self):
        item = self.your_battlefield_list.currentItem()
        if item: self.dispatcher.send_activate_ability(item.text().split(" ")[0], targets=[], cost_payment={"tap": True, "mana": {}})

    def on_attack_clicked(self):
        if self.state.phase != "DECLARE_ATTACKERS": return
        ids = [self.your_battlefield_list.item(i).text().split(" ")[0] for i in range(self.your_battlefield_list.count()) if self.your_battlefield_list.item(i).isSelected()]
        opponent = self.presenter.opponent_id()
        self.dispatcher.send_declare_attackers([{"creature_id": card_id, "target": opponent} for card_id in ids])

    def on_suspend_clicked(self):
        item = self.hand_list.currentItem()
        if item and CardCatalog.base_card_id(item.text()) == "rift_bolt": self.dispatcher.send_suspend_card(item.text(), {"R": 1})

    def closeEvent(self, event):
        self.dispatcher.connection.close()
        event.accept()
