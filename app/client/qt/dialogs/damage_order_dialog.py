from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton
)
from PySide6.QtCore import Qt

class DamageOrderDialog(QDialog):
    def __init__(self, attacker_id: str, blockers: list, parent=None):
        super().__init__(parent)
        self.attacker_id = attacker_id
        self.blockers = list(blockers)
        self.ordered_blockers = []
        self.setWindowTitle(f"Assign Damage Order for {attacker_id}")
        self.setMinimumWidth(380)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        info_lbl = QLabel(f"Attacker: {self.attacker_id}\nOrder blockers (top blocker receives lethal damage first):")
        info_lbl.setStyleSheet("font-weight: bold; color: #89b4fa;")
        info_lbl.setWordWrap(True)
        layout.addWidget(info_lbl)

        h_layout = QHBoxLayout()
        self.list_widget = QListWidget()
        for b in self.blockers:
            self.list_widget.addItem(b)
        h_layout.addWidget(self.list_widget)

        btn_layout = QVBoxLayout()
        btn_up = QPushButton("Move Up")
        btn_up.clicked.connect(self._move_up)
        btn_down = QPushButton("Move Down")
        btn_down.clicked.connect(self._move_down)

        btn_layout.addWidget(btn_up)
        btn_layout.addWidget(btn_down)
        btn_layout.addStretch()
        h_layout.addLayout(btn_layout)

        layout.addLayout(h_layout)

        self.btn_confirm = QPushButton("Confirm Order")
        self.btn_confirm.setObjectName("btn_primary")
        self.btn_confirm.clicked.connect(self._on_confirm)
        layout.addWidget(self.btn_confirm)

    def _move_up(self):
        row = self.list_widget.currentRow()
        if row > 0:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row - 1, item)
            self.list_widget.setCurrentRow(row - 1)

    def _move_down(self):
        row = self.list_widget.currentRow()
        if row >= 0 and row < self.list_widget.count() - 1:
            item = self.list_widget.takeItem(row)
            self.list_widget.insertItem(row + 1, item)
            self.list_widget.setCurrentRow(row + 1)

    def _on_confirm(self):
        self.ordered_blockers = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        self.accept()
