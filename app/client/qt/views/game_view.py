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

class GameView(QWidget):
    card_selected = Signal(str)
    permanent_selected = Signal(str)
    stack_item_selected = Signal(str)
    action_submitted = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.local_player_id = "player_1"
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
        self.battlefield.permanent_clicked.connect(self.permanent_selected)
        self.local_hud = PlayerHud("You", is_local=True)
        self.hand_widget = HandWidget()
        self.hand_widget.card_selected.connect(self.card_selected)

        left_layout.addWidget(self.opp_hud)
        left_layout.addWidget(self.battlefield, 1) # Expandable battlefield
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
        self.stack_widget.stack_item_clicked.connect(self.stack_item_selected)
        self.event_log = EventLogWidget()

        right_layout.addWidget(self.stack_widget, 1)
        right_layout.addWidget(self.event_log, 1)

        splitter.addWidget(right_widget)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 1)

        main_layout.addWidget(splitter, 1)

    def update_view(self, state: dict, local_player_id: str):
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

        # Update Opponent HUD
        self.opp_hud.update_hud(
            player_id=opp_id,
            life=lifes.get(opp_id, 20),
            hand_cnt=h_counts.get(opp_id, 0),
            lib_cnt=libs.get(opp_id, 0),
            gy_cnt=len(gys.get(opp_id, [])),
            is_active=(active_p == opp_id),
            has_priority=(prio_p == opp_id)
        )

        # Update Local HUD
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

        # Update Battlefield
        bf_data = state.get("battlefield", {})
        self.battlefield.update_battlefield(bf_data, self.local_player_id)

        # Update Hand
        self.hand_widget.update_hand(local_hand)

        # Update Stack
        stack_items = state.get("stack", [])
        self.stack_widget.update_stack(stack_items)

    def log_event(self, msg: str):
        self.event_log.log_event(msg)
