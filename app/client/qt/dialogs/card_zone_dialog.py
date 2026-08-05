from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QPushButton
)

class CardZoneDialog(QDialog):
    def __init__(self, zone_name: str, card_ids: list, parent=None):
        super().__init__(parent)
        self.zone_name = zone_name
        self.card_ids = list(card_ids)

        self.setWindowTitle(f"Zone Browser - {zone_name}")
        self.setMinimumWidth(350)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel(f"Zone: {self.zone_name} ({len(self.card_ids)} cards)")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #89b4fa;")
        layout.addWidget(title)

        self.list_widget = QListWidget()
        for c in self.card_ids:
            self.list_widget.addItem(c)
        layout.addWidget(self.list_widget)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close)
