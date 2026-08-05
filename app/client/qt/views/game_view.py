from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter, QLabel, QFrame, QPushButton
)
from PySide6.QtCore import Signal, Qt
from app.client.qt.widgets.phase_bar import PhaseBarWidget
from app.client.qt.widgets.player_hud import PlayerHud
from app.client.qt.widgets.battlefield_view import BattlefieldView
from app.client.qt.widgets.hand_widget import HandWidget
from app.client.qt.widgets.stack_widget import StackWidget
from app.client.qt.widgets.event_log import EventLogWidget
from app.client.qt.widgets.action_panel import ActionPanel
from app.client.qt.models.interaction_state import InteractionState

class GameView(QWidget):
    action_submitted = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.local_player_id = "player_1"
        self.interaction = InteractionState()
        self.current_state = {}
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # 1. Top Phase Bar
        self.phase_bar = PhaseBarWidget()
        main_layout.addWidget(self.phase_bar)

        # 2. Main Horizontal Splitter (Board View Left, Sidebar Right)
        splitter = QSplitter(Qt.Horizontal)

        # Left Section: Opponent HUD, Battlefield, Local HUD, Local Hand
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.opp_hud = PlayerHud("Opponent", is_local=False)
        self.battlefield = BattlefieldView()
        self.battlefield.permanent_clicked.connect(self._on_permanent_clicked)
        self.local_hud = PlayerHud("You", is_local=True)
        self.hand_widget = HandWidget()
        self.hand_widget.card_selected.connect(self._on_hand_card_clicked)

        left_layout.addWidget(self.opp_hud)
        left_layout.addWidget(self.battlefield, 1)
        left_layout.addWidget(self.local_hud)
        left_layout.addWidget(self.hand_widget)

        splitter.addWidget(left_widget)

        # Right Section: Narrow Sidebar for Stack & Event Log
        right_widget = QWidget()
        right_widget.setMaximumWidth(360)
        right_widget.setMinimumWidth(260)
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(6)

        self.stack_widget = StackWidget()
        self.stack_widget.stack_item_clicked.connect(self._on_stack_item_clicked)
        self.event_log = EventLogWidget()

        right_layout.addWidget(self.stack_widget, 1)
        right_layout.addWidget(self.event_log, 1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter, 1)

        # 3. Contextual Action Panel
        self.action_panel = ActionPanel()
        self.action_panel.pass_priority_requested.connect(self._on_pass_priority)
        self.action_panel.play_land_requested.connect(self._on_play_land)
        self.action_panel.cast_spell_requested.connect(self._on_cast_spell)
        self.action_panel.activate_ability_requested.connect(self._on_activate_ability)
        self.action_panel.cancel_selection_requested.connect(self._on_cancel_selection)
        self.action_panel.concede_requested.connect(self._on_concede)

        main_layout.addWidget(self.action_panel)

    def update_view(self, state: dict, local_player_id: str):
        self.current_state = state
        self.local_player_id = local_player_id or "player_1"
        
        turn = state.get("turn", 0)
        phase = state.get("phase", "LOBBY")
        active_p = state.get("active_player", "")
        prio_p = state.get("priority_holder", "")

        self.phase_bar.update_bar(turn, phase, active_p, prio_p)

        lifes = state.get("life_totals", {})
        libs = state.get("library_counts", {})
        gys = state.get("graveyard", {})
        h_counts = state.get("hand_counts", {})

        opp_p = [p for p in lifes.keys() if p != self.local_player_id]
        opp_id = opp_p[0] if opp_p else ("player_2" if self.local_player_id == "player_1" else "player_1")

        self.opp_hud.update_hud(
            player_id=opp_id,
            life=lifes.get(opp_id, 20),
            hand_cnt=h_counts.get(opp_id, 0),
            lib_cnt=libs.get(opp_id, 0),
            gy_cnt=len(gys.get(opp_id, [])),
            is_active=(active_p == opp_id),
            has_priority=(prio_p == opp_id)
        )

        local_hand = state.get("hand", [])
        self.local_hud.update_hud(
            player_id=self.local_player_id,
            life=lifes.get(self.local_player_id, 20),
            hand_cnt=len(local_hand),
            lib_cnt=libs.get(self.local_player_id, 0),
            gy_cnt=len(gys.get(self.local_player_id, [])),
            is_active=(active_p == self.local_player_id),
            has_priority=(prio_p == self.local_player_id)
        )

        bf_data = state.get("battlefield", {})
        self.battlefield.update_battlefield(bf_data, self.local_player_id)

        self.hand_widget.update_hand(local_hand)

        stack_items = state.get("stack", [])
        self.stack_widget.update_stack(stack_items)

        has_priority = (prio_p == self.local_player_id)
        self.interaction.action_pending = False
        self._refresh_action_panel(has_priority)

    def _refresh_action_panel(self, has_priority: bool):
        self.action_panel.update_context(
            selected_card=self.interaction.selected_hand_card,
            selected_perm=self.interaction.selected_permanent,
            targets=self.interaction.selected_targets,
            has_priority=has_priority,
            action_pending=self.interaction.action_pending
        )

    def _on_hand_card_clicked(self, cid: str):
        if self.interaction.is_targeting_mode:
            # If in targeting mode, card in hand cannot be targeted
            return
        self.interaction.selected_hand_card = cid
        self.interaction.selected_permanent = ""
        self.interaction.selected_targets = []
        prio_p = self.current_state.get("priority_holder", "")
        self._refresh_action_panel(prio_p == self.local_player_id)

    def _on_permanent_clicked(self, perm_id: str):
        if self.interaction.selected_hand_card or self.interaction.selected_permanent:
            # Add as target!
            if perm_id not in self.interaction.selected_targets:
                self.interaction.selected_targets.append(perm_id)
                self.log_event(f"Target selected: {perm_id}")
        else:
            self.interaction.selected_permanent = perm_id
            self.interaction.selected_hand_card = ""
            self.interaction.selected_targets = []

        prio_p = self.current_state.get("priority_holder", "")
        self._refresh_action_panel(prio_p == self.local_player_id)

    def _on_stack_item_clicked(self, sid: str):
        if self.interaction.selected_hand_card or self.interaction.selected_permanent:
            if sid not in self.interaction.selected_targets:
                self.interaction.selected_targets.append(sid)
                self.log_event(f"Stack target selected: {sid}")
            prio_p = self.current_state.get("priority_holder", "")
            self._refresh_action_panel(prio_p == self.local_player_id)

    def _on_pass_priority(self):
        seq = self.current_state.get("seq_num", 0)
        self.interaction.action_pending = True
        self.action_submitted.emit({"type": "PRIORITY_PASS", "seq_num": seq})
        self.log_event("Action Sent: Pass Priority")

    def _on_play_land(self, cid: str):
        seq = self.current_state.get("seq_num", 0)
        self.interaction.action_pending = True
        self.action_submitted.emit({"type": "PLAY_LAND", "seq_num": seq, "card_id": cid})
        self.log_event(f"Action Sent: Play Land ({cid})")

    def _on_cast_spell(self, cid: str, targets: list):
        seq = self.current_state.get("seq_num", 0)
        self.interaction.action_pending = True
        self.action_submitted.emit({
            "type": "CAST_SPELL",
            "seq_num": seq,
            "card_id": cid,
            "targets": targets,
            "mana_payment": {}
        })
        self.log_event(f"Action Sent: Cast {cid} (Targets: {targets})")

    def _on_activate_ability(self, perm_id: str, ability_idx: int, targets: list):
        seq = self.current_state.get("seq_num", 0)
        self.interaction.action_pending = True
        self.action_submitted.emit({
            "type": "ACTIVATE_ABILITY",
            "seq_num": seq,
            "permanent_id": perm_id,
            "ability_index": ability_idx,
            "targets": targets,
            "mana_payment": {}
        })
        self.log_event(f"Action Sent: Activate Ability on {perm_id}")

    def _on_cancel_selection(self):
        self.interaction.clear_selections()
        prio_p = self.current_state.get("priority_holder", "")
        self._refresh_action_panel(prio_p == self.local_player_id)

    def _on_concede(self):
        seq = self.current_state.get("seq_num", 0)
        self.action_submitted.emit({"type": "CONCEDE", "seq_num": seq, "player_id": self.local_player_id})
        self.log_event("Action Sent: Concede")

    def log_event(self, msg: str):
        self.event_log.log_event(msg)
