from PySide6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QLabel, QMessageBox
from PySide6.QtCore import Signal, Qt
from app.shared.cards import CardCatalog

class ActionPanel(QFrame):
    pass_priority_requested = Signal()
    play_land_requested = Signal(str)
    cast_spell_requested = Signal(str, list)
    activate_ability_requested = Signal(str, int, list)
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

        # Action status label
        self.status_lbl = QLabel("Action Status: Ready")
        self.status_lbl.setStyleSheet("color: #a6adc8; font-weight: bold;")
        self.layout.addWidget(self.status_lbl)

        self.layout.addStretch()

        # Dynamic action button container
        self.btn_pass = QPushButton("Pass Priority")
        self.btn_pass.setObjectName("btn_primary")
        self.btn_pass.clicked.connect(self._on_pass_clicked)

        self.btn_play_land = QPushButton("Play Land")
        self.btn_play_land.setObjectName("btn_success")
        self.btn_play_land.clicked.connect(self._on_play_land_clicked)

        self.btn_cast = QPushButton("Cast Spell")
        self.btn_cast.setObjectName("btn_primary")
        self.btn_cast.clicked.connect(self._on_cast_clicked)

        self.btn_activate = QPushButton("Activate Ability")
        self.btn_activate.setObjectName("btn_primary")
        self.btn_activate.clicked.connect(self._on_activate_clicked)

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)

        self.btn_concede = QPushButton("Concede")
        self.btn_concede.setObjectName("btn_danger")
        self.btn_concede.clicked.connect(self._on_concede_clicked)

        self.layout.addWidget(self.btn_pass)
        self.layout.addWidget(self.btn_play_land)
        self.layout.addWidget(self.btn_cast)
        self.layout.addWidget(self.btn_activate)
        self.layout.addWidget(self.btn_cancel)
        self.layout.addWidget(self.btn_concede)

        # Default state
        self.update_context(selected_card="", selected_perm="", targets=[], has_priority=True, action_pending=False)

    def update_context(self, selected_card: str, selected_perm: str, targets: list, has_priority: bool, action_pending: bool):
        # Hide all by default
        self.btn_pass.setVisible(False)
        self.btn_play_land.setVisible(False)
        self.btn_cast.setVisible(False)
        self.btn_activate.setVisible(False)
        self.btn_cancel.setVisible(False)
        self.btn_concede.setVisible(True)

        if action_pending:
            self.status_lbl.setText("Waiting for server response...")
            self.status_lbl.setStyleSheet("color: #f9e2af; font-weight: bold;")
            self.btn_concede.setEnabled(True)
            return

        if not has_priority:
            self.status_lbl.setText("Waiting for opponent priority...")
            self.status_lbl.setStyleSheet("color: #a6adc8; font-style: italic;")
            return

        self.status_lbl.setText("Your Priority")
        self.status_lbl.setStyleSheet("color: #a6e3a1; font-weight: bold;")

        self.current_card = selected_card
        self.current_perm = selected_perm
        self.current_targets = targets

        if selected_card:
            defn = self.catalog.get_definition(selected_card)
            self.btn_cancel.setVisible(True)

            if defn and defn.is_land():
                self.btn_play_land.setVisible(True)
                self.btn_play_land.setText(f"Play Land ({defn.name})")
            else:
                self.btn_cast.setVisible(True)
                target_str = f" ({len(targets)} target(s) selected)" if targets else ""
                self.btn_cast.setText(f"Cast Spell{target_str}")
        elif selected_perm:
            self.btn_cancel.setVisible(True)
            self.btn_activate.setVisible(True)
            target_str = f" ({len(targets)} target(s) selected)" if targets else ""
            self.btn_activate.setText(f"Activate Ability{target_str}")
        else:
            self.btn_pass.setVisible(True)

    def _on_pass_clicked(self):
        self.pass_priority_requested.emit()

    def _on_play_land_clicked(self):
        if self.current_card:
            self.play_land_requested.emit(self.current_card)

    def _on_cast_clicked(self):
        if self.current_card:
            self.cast_spell_requested.emit(self.current_card, self.current_targets)

    def _on_activate_clicked(self):
        if self.current_perm:
            self.activate_ability_requested.emit(self.current_perm, 0, self.current_targets)

    def _on_cancel_clicked(self):
        self.cancel_selection_requested.emit()

    def _on_concede_clicked(self):
        reply = QMessageBox.question(
            self, "Confirm Concession", "Are you sure you want to concede the game?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.concede_requested.emit()
