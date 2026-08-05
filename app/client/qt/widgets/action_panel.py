from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QLabel, QMessageBox
from PySide6.QtCore import Signal, Qt
from app.shared.cards import CardCatalog

class ActionPanel(QFrame):
    pass_priority_requested = Signal()
    play_land_requested = Signal(str)
    cast_spell_requested = Signal(str, list)
    activate_ability_requested = Signal(str, int, list)
    confirm_attackers_requested = Signal()
    declare_no_attackers_requested = Signal()
    confirm_blockers_requested = Signal()
    declare_no_blockers_requested = Signal()
    cancel_selection_requested = Signal()
    concede_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.catalog = CardCatalog.get_instance()
        self._init_ui()

    def _init_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setFixedHeight(55)
        self.setStyleSheet("""
            QFrame {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 6px;
                padding: 4px;
            }
        """)

        self.layout = QHBoxLayout(self)
        self.layout.setContentsMargins(10, 4, 10, 4)
        self.layout.setSpacing(10)

        self.status_lbl = QLabel("Action Status: Ready")
        self.status_lbl.setStyleSheet("color: #a6adc8; font-weight: bold;")
        self.layout.addWidget(self.status_lbl)

        self.layout.addStretch()

        self.btn_pass = QPushButton("Pass Priority")
        self.btn_pass.setObjectName("btn_primary")
        self.btn_pass.clicked.connect(self.pass_priority_requested.emit)

        self.btn_play_land = QPushButton("Play Land")
        self.btn_play_land.setObjectName("btn_success")
        self.btn_play_land.clicked.connect(self._on_play_land_clicked)

        self.btn_cast = QPushButton("Cast Spell")
        self.btn_cast.setObjectName("btn_primary")
        self.btn_cast.clicked.connect(self._on_cast_clicked)

        self.btn_activate = QPushButton("Activate Ability")
        self.btn_activate.setObjectName("btn_primary")
        self.btn_activate.clicked.connect(self._on_activate_clicked)

        self.btn_confirm_attackers = QPushButton("Confirm Attackers")
        self.btn_confirm_attackers.setObjectName("btn_danger")
        self.btn_confirm_attackers.clicked.connect(self.confirm_attackers_requested.emit)

        self.btn_no_attackers = QPushButton("Declare No Attackers")
        self.btn_no_attackers.clicked.connect(self.declare_no_attackers_requested.emit)

        self.btn_confirm_blockers = QPushButton("Confirm Blockers")
        self.btn_confirm_blockers.setObjectName("btn_success")
        self.btn_confirm_blockers.clicked.connect(self.confirm_blockers_requested.emit)

        self.btn_no_blockers = QPushButton("Declare No Blockers")
        self.btn_no_blockers.clicked.connect(self.declare_no_blockers_requested.emit)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.cancel_selection_requested.emit)

        self.btn_concede = QPushButton("Concede")
        self.btn_concede.setObjectName("btn_danger")
        self.btn_concede.clicked.connect(self._on_concede_clicked)

        self.layout.addWidget(self.btn_pass)
        self.layout.addWidget(self.btn_play_land)
        self.layout.addWidget(self.btn_cast)
        self.layout.addWidget(self.btn_activate)
        self.layout.addWidget(self.btn_confirm_attackers)
        self.layout.addWidget(self.btn_no_attackers)
        self.layout.addWidget(self.btn_confirm_blockers)
        self.layout.addWidget(self.btn_no_blockers)
        self.layout.addWidget(self.btn_cancel)
        self.layout.addWidget(self.btn_concede)

        self.update_context(selected_card="", selected_perm="", targets=[], phase="LOBBY", has_priority=True, action_pending=False)

    def update_context(self, selected_card: str, selected_perm: str, targets: list, phase: str, has_priority: bool, action_pending: bool, attacker_count: int = 0, blocker_count: int = 0):
        # Hide all by default
        self.btn_pass.setVisible(False)
        self.btn_play_land.setVisible(False)
        self.btn_cast.setVisible(False)
        self.btn_activate.setVisible(False)
        self.btn_confirm_attackers.setVisible(False)
        self.btn_no_attackers.setVisible(False)
        self.btn_confirm_blockers.setVisible(False)
        self.btn_no_blockers.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.btn_concede.setVisible(True)

        if action_pending:
            self.status_lbl.setText("Waiting for server response...")
            self.status_lbl.setStyleSheet("color: #f9e2af; font-weight: bold;")
            return

        if not has_priority and phase not in ("DECLARE_ATTACKERS", "DECLARE_BLOCKERS"):
            self.status_lbl.setText("Waiting for opponent priority...")
            self.status_lbl.setStyleSheet("color: #a6adc8; font-style: italic;")
            return

        self.current_card = selected_card
        self.current_perm = selected_perm
        self.current_targets = targets

        if phase == "DECLARE_ATTACKERS":
            self.status_lbl.setText(f"Declare Attackers ({attacker_count} selected)")
            self.status_lbl.setStyleSheet("color: #f38ba8; font-weight: bold;")
            self.btn_confirm_attackers.setVisible(True)
            self.btn_no_attackers.setVisible(True)
            self.btn_cancel.setVisible(True)
            return

        if phase == "DECLARE_BLOCKERS":
            self.status_lbl.setText(f"Declare Blockers ({blocker_count} assigned)")
            self.status_lbl.setStyleSheet("color: #a6e3a1; font-weight: bold;")
            self.btn_confirm_blockers.setVisible(True)
            self.btn_no_blockers.setVisible(True)
            self.btn_cancel.setVisible(True)
            return

        self.status_lbl.setText("Your Priority")
        self.status_lbl.setStyleSheet("color: #a6e3a1; font-weight: bold;")

        if selected_card:
            defn = self.catalog.get_definition(selected_card)
            self.btn_cancel.setVisible(True)
            if defn and defn.is_land():
                self.btn_play_land.setVisible(True)
                self.btn_play_land.setText(f"Play Land ({defn.name})")
            else:
                self.btn_cast.setVisible(True)
                target_str = f" ({len(targets)} target(s))" if targets else ""
                self.btn_cast.setText(f"Cast Spell{target_str}")
        elif selected_perm:
            self.btn_cancel.setVisible(True)
            self.btn_activate.setVisible(True)
            target_str = f" ({len(targets)} target(s))" if targets else ""
            self.btn_activate.setText(f"Activate Ability{target_str}")
        else:
            self.btn_pass.setVisible(True)

    def _on_play_land_clicked(self):
        if self.current_card:
            self.play_land_requested.emit(self.current_card)

    def _on_cast_clicked(self):
        if self.current_card:
            self.cast_spell_requested.emit(self.current_card, self.current_targets)

    def _on_activate_clicked(self):
        if self.current_perm:
            self.activate_ability_requested.emit(self.current_perm, 0, self.current_targets)

    def _on_concede_clicked(self):
        reply = QMessageBox.question(
            self, "Confirm Concession", "Are you sure you want to concede the game?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.concede_requested.emit()
