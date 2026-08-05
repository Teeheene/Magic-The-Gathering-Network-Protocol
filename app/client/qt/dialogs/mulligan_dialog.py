from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton
)
from PySide6.QtCore import Qt

class MulliganDialog(QDialog):
    def __init__(self, hand: list, mulligans_taken: int = 0, parent=None):
        super().__init__(parent)
        self.hand = list(hand)
        self.mulligans_taken = mulligans_taken
        self.cards_to_bottom = []
        self.keep_choice = False

        self.setWindowTitle("London Mulligan Decision")
        self.setMinimumWidth(400)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel(f"Opening Hand (Mulligans Taken: {self.mulligans_taken})")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #89b4fa;")
        layout.addWidget(title)

        if self.mulligans_taken > 0:
            sub = QLabel(f"Select exactly {self.mulligans_taken} card(s) to place on the bottom of your library if you Keep:")
            sub.setStyleSheet("color: #f9e2af;")
            sub.setWordWrap(True)
            layout.addWidget(sub)

        self.list_widget = QListWidget()
        if self.mulligans_taken > 0:
            self.list_widget.setSelectionMode(QListWidget.MultiSelection)

        for c in self.hand:
            self.list_widget.addItem(c)
        layout.addWidget(self.list_widget)

        btn_layout = QHBoxLayout()
        self.btn_keep = QPushButton("Keep Hand")
        self.btn_keep.setObjectName("btn_success")
        self.btn_keep.clicked.connect(self._on_keep)

        self.btn_mulligan = QPushButton("Mulligan")
        self.btn_mulligan.setObjectName("btn_danger")
        self.btn_mulligan.clicked.connect(self._on_mulligan)

        btn_layout.addWidget(self.btn_keep)
        btn_layout.addWidget(self.btn_mulligan)
        layout.addLayout(btn_layout)

    def _on_keep(self):
        if self.mulligans_taken > 0:
            selected_items = self.list_widget.selectedItems()
            if len(selected_items) != self.mulligans_taken:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Invalid Selection", f"You must select exactly {self.mulligans_taken} card(s) to bottom.")
                return
            self.cards_to_bottom = [item.text() for item in selected_items]

        self.keep_choice = True
        self.accept()

    def _on_mulligan(self):
        self.keep_choice = False
        self.cards_to_bottom = []
        self.accept()
