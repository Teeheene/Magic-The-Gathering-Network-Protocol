from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout
from PySide6.QtCore import Qt

class PlayerHud(QFrame):
    def __init__(self, player_label: str = "Player", is_local: bool = False, parent=None):
        super().__init__(parent)
        self.player_label = player_label
        self.is_local = is_local
        self._init_ui()

    def _init_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #1e1e2e;
                border: 1px solid #313244;
                border-radius: 6px;
                padding: 6px;
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)

        # Name & Status
        name_box = QVBoxLayout()
        self.name_lbl = QLabel(self.player_label)
        self.name_lbl.setStyleSheet("font-size: 14px; font-weight: bold; color: #89b4fa;")
        
        self.role_lbl = QLabel("Waiting...")
        self.role_lbl.setStyleSheet("font-size: 11px; color: #a6adc8;")
        name_box.addWidget(self.name_lbl)
        name_box.addWidget(self.role_lbl)
        layout.addLayout(name_box)

        layout.addStretch()

        # Stats (Life, Library, Hand, Graveyard)
        stats_box = QHBoxLayout()
        stats_box.setSpacing(20)

        self.life_lbl = QLabel("Life: 20")
        self.life_lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #a6e3a1;")

        self.hand_lbl = QLabel("Hand: 0")
        self.hand_lbl.setStyleSheet("font-size: 13px; color: #cdd6f4;")

        self.lib_lbl = QLabel("Library: 0")
        self.lib_lbl.setStyleSheet("font-size: 13px; color: #cdd6f4;")

        self.gy_lbl = QLabel("Graveyard: 0")
        self.gy_lbl.setStyleSheet("font-size: 13px; color: #cdd6f4;")

        stats_box.addWidget(self.life_lbl)
        stats_box.addWidget(self.hand_lbl)
        stats_box.addWidget(self.lib_lbl)
        stats_box.addWidget(self.gy_lbl)

        layout.addLayout(stats_box)

    def update_hud(self, player_id: str, life: int, hand_cnt: int, lib_cnt: int, gy_cnt: int, is_active: bool = False, has_priority: bool = False):
        prefix = "You" if self.is_local else "Opponent"
        self.name_lbl.setText(f"{prefix} ({player_id or 'Waiting...'})")

        self.life_lbl.setText(f"Life: {life}")
        self.hand_lbl.setText(f"Hand: {hand_cnt}")
        self.lib_lbl.setText(f"Library: {lib_cnt}")
        self.gy_lbl.setText(f"GY: {gy_cnt}")

        status_parts = []
        if is_active:
            status_parts.append("[ACTIVE TURN]")
        if has_priority:
            status_parts.append("[PRIORITY]")
        
        if status_parts:
            self.role_lbl.setText(" ".join(status_parts))
            self.role_lbl.setStyleSheet("font-size: 11px; font-weight: bold; color: #f9e2af;")
        else:
            self.role_lbl.setText("Waiting for priority...")
            self.role_lbl.setStyleSheet("font-size: 11px; color: #a6adc8;")
