from PySide6.QtWidgets import QMainWindow, QStackedWidget, QMessageBox, QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Slot, Qt
from app.client.controller import ClientController
from app.client.qt.theme import MTGTheme
from app.client.qt.views.connection_view import ConnectionView
from app.client.qt.views.lobby_view import LobbyView
from app.client.qt.views.game_view import GameView
from app.client.qt.views.game_over_view import GameOverView
from app.client.actions import ClientActionFactory

class MainWindow(QMainWindow):
    def __init__(self, controller: ClientController, host: str = None, port: int = None):
        super().__init__()
        self.controller = controller
        self.default_host = host
        self.default_port = port

        self.setWindowTitle("MTGNP - Magic: The Gathering Network Protocol Client (PySide6)")
        self.resize(1280, 850)
        self.setMinimumSize(1024, 700)
        self.setStyleSheet(MTGTheme.QSS)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.connection_view = ConnectionView()
        self.lobby_view = LobbyView()
        self.game_view = GameView()
        self.game_over_view = GameOverView()

        self.stack.addWidget(self.connection_view)  # index 0
        self.stack.addWidget(self.lobby_view)       # index 1
        self.stack.addWidget(self.game_view)        # index 2
        self.stack.addWidget(self.game_over_view)   # index 3

        self._wire_signals()

        if self.default_host and self.default_port:
            self.connection_view.host_input.setText(str(self.default_host))
            self.connection_view.port_input.setText(str(self.default_port))
            self.controller.connect_server(str(self.default_host), int(self.default_port))

    def _wire_signals(self):
        self.connection_view.connect_requested.connect(self.controller.connect_server)
        self.lobby_view.ready_requested.connect(self._on_ready_requested)
        self.game_view.action_submitted.connect(self.controller.send_action)
        self.game_over_view.return_lobby_requested.connect(self._on_return_lobby)

        self.controller.connection_changed.connect(self._on_connection_changed)
        self.controller.state_changed.connect(self._on_state_changed)
        self.controller.protocol_error.connect(self._on_protocol_error)
        self.controller.game_over.connect(self._on_game_over)
        self.controller.mulligan_prompt.connect(self._on_mulligan_prompt)
        self.controller.trigger_prompt.connect(self._on_trigger_prompt)
        self.controller.trigger_order_prompt.connect(self._on_trigger_order_prompt)
        self.controller.discard_prompt.connect(self._on_discard_prompt)
        self.controller.damage_order_prompt.connect(self._on_damage_order_prompt)

    @Slot(str)
    def _on_connection_changed(self, status: str):
        if status == "connected":
            self.connection_view.set_status("Connected!")
            self.stack.setCurrentIndex(1) # Show Lobby View
        elif status == "disconnected":
            self.connection_view.set_status("Disconnected from server", is_error=True)
            self.connection_view.btn_connect.setEnabled(True)
            self.stack.setCurrentIndex(0) # Show Connection View
        elif status == "connecting":
            self.connection_view.set_status("Connecting to server...")

    @Slot(dict)
    def _on_state_changed(self, current_state: dict):
        pid = self.controller.state.player_id
        phase = current_state.get("phase", "LOBBY")
        
        self.lobby_view.update_state(pid, current_state)

        if phase not in ("LOBBY", "") and not self.controller.state.is_game_over:
            self.game_view.update_view(current_state, pid)
            if self.stack.currentIndex() != 2:
                self.stack.setCurrentIndex(2)

    @Slot(dict)
    def _on_ready_requested(self, deck_name: str):
        pdu = ClientActionFactory.player_ready(self.controller.state.last_seq_num, deck_name)
        self.controller.send_action(pdu)

    @Slot(dict)
    def _on_protocol_error(self, err_pdu: dict):
        code = err_pdu.get("code", "ERROR")
        msg = err_pdu.get("message", "An unexpected protocol error occurred.")
        QMessageBox.warning(self, f"Protocol Error ({code})", f"[{code}]\n{msg}")

    @Slot(dict)
    def _on_game_over(self, game_over_pdu: dict):
        winner = game_over_pdu.get("winner_id", "")
        reason = game_over_pdu.get("reason", "Conceded / Match Ended")
        local_p = self.controller.state.player_id
        
        self.game_over_view.set_result(winner, reason, local_p)
        self.stack.setCurrentIndex(3) # Show Game Over View

    @Slot()
    def _on_return_lobby(self):
        self.controller.state.is_game_over = False
        self.stack.setCurrentIndex(1)

    @Slot(dict)
    def _on_mulligan_prompt(self, pdu: dict):
        from app.client.qt.dialogs.mulligan_dialog import MulliganDialog
        hand = self.controller.state.current_state.get("hand", [])
        taken = pdu.get("mulligans_taken", 0)
        dlg = MulliganDialog(hand=hand, mulligans_taken=taken, parent=self)
        if dlg.exec():
            pdu_out = ClientActionFactory.mulligan_choice(
                seq_num=self.controller.state.last_seq_num,
                keep=dlg.keep_choice,
                cards_to_bottom=dlg.cards_to_bottom
            )
            self.controller.send_action(pdu_out)

    @Slot(dict)
    def _on_trigger_prompt(self, pdu: dict):
        from app.client.qt.dialogs.trigger_choice_dialog import TriggerChoiceDialog
        dlg = TriggerChoiceDialog(pdu=pdu, parent=self)
        if dlg.exec():
            pdu_out = ClientActionFactory.trigger_choice_response(
                seq_num=self.controller.state.last_seq_num,
                trigger_id=pdu.get("trigger_id", ""),
                accept=dlg.accept_choice,
                targets=dlg.selected_targets
            )
            self.controller.send_action(pdu_out)

    @Slot(dict)
    def _on_trigger_order_prompt(self, pdu: dict):
        from app.client.qt.dialogs.trigger_order_dialog import TriggerOrderDialog
        trgs = pdu.get("trigger_ids", [])
        dlg = TriggerOrderDialog(trigger_ids=trgs, parent=self)
        if dlg.exec():
            pdu_out = ClientActionFactory.trigger_order_response(
                seq_num=self.controller.state.last_seq_num,
                trigger_order=dlg.ordered_triggers
            )
            self.controller.send_action(pdu_out)

    @Slot(dict)
    def _on_discard_prompt(self, pdu: dict):
        from app.client.qt.dialogs.discard_dialog import DiscardDialog
        hand = self.controller.state.current_state.get("hand", [])
        cnt = pdu.get("count", 1)
        dlg = DiscardDialog(hand=hand, count=cnt, parent=self)
        if dlg.exec():
            pdu_out = ClientActionFactory.discard(
                seq_num=self.controller.state.last_seq_num,
                card_ids=dlg.discarded_cards
            )
            self.controller.send_action(pdu_out)

    @Slot(dict)
    def _on_damage_order_prompt(self, pdu: dict):
        from app.client.qt.dialogs.damage_order_dialog import DamageOrderDialog
        atk_id = pdu.get("attacker_id", "")
        blks = pdu.get("blockers", [])
        dlg = DamageOrderDialog(attacker_id=atk_id, blockers=blks, parent=self)
        if dlg.exec():
            pdu_out = ClientActionFactory.assign_damage_order(
                seq_num=self.controller.state.last_seq_num,
                attacker_id=atk_id,
                blocker_order=dlg.ordered_blockers
            )
            self.controller.send_action(pdu_out)
