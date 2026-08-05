from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QListWidget, QPushButton, QMessageBox
)

class DiscardDialog(QDialog):
    def __init__(self, hand: list, count: int = 1, parent=None):
        super().__init__(parent)
        self.hand = list(hand)
        self.required_count = count
        self.discarded_cards = []

        self.setWindowTitle("Discard Required")
        self.setMinimumWidth(380)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel(f"Discard to Hand Size (Select exactly {self.required_count} card(s))")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #f38ba8;")
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)
        for c in self.hand:
            self.list_widget.addItem(c)
        layout.addWidget(self.list_widget)

        self.btn_confirm = QPushButton("Confirm Discard")
        self.btn_confirm.setObjectName("btn_danger")
        self.btn_confirm.clicked.connect(self._on_confirm)
        layout.addWidget(self.btn_confirm)

    def _on_confirm(self):
        selected_items = self.list_widget.selectedItems()
        if len(selected_items) != self.required_count:
            QMessageBox.warning(self, "Invalid Selection", f"You must select exactly {self.required_count} card(s) to discard.")
            return

        self.discarded_cards = [item.text() for item in selected_items]
        self.accept()
