from typing import Any, List, Optional
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)


class MulliganDialog(QDialog):
    """Dialog for London Mulligan choices (Keep vs Mulligan, and card bottom selection)."""

    def __init__(self, hand_cards: List[str], count_to_bottom: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mulligan Choice")
        self.count_to_bottom = count_to_bottom
        self.selected_bottom_cards: List[str] = []

        layout = QVBoxLayout(self)

        if count_to_bottom == 0:
            layout.addWidget(QLabel("Would you like to Keep this hand or Mulligan?"))
            btn_box = QHBoxLayout()
            self.keep_btn = QPushButton("Keep")
            self.mull_btn = QPushButton("Mulligan")
            self.keep_btn.clicked.connect(self.accept_keep)
            self.mull_btn.clicked.connect(self.accept_mulligan)
            btn_box.addWidget(self.keep_btn)
            btn_box.addWidget(self.mull_btn)
            layout.addLayout(btn_box)
            self.choice = "KEEP"
        else:
            layout.addWidget(
                QLabel(f"Select exactly {count_to_bottom} card(s) to place on the bottom of your library:")
            )
            self.card_list = QListWidget()
            self.card_list.setSelectionMode(QListWidget.MultiSelection)
            for card_id in hand_cards:
                item = QListWidgetItem(card_id)
                self.card_list.addItem(item)
            layout.addWidget(self.card_list)

            self.confirm_btn = QPushButton("Confirm Cards to Bottom")
            self.confirm_btn.clicked.connect(self.accept_bottom_selection)
            layout.addWidget(self.confirm_btn)
            self.choice = "BOTTOM"

    def accept_keep(self):
        self.choice = "KEEP"
        self.accept()

    def accept_mulligan(self):
        self.choice = "MULLIGAN"
        self.accept()

    def accept_bottom_selection(self):
        selected_items = self.card_list.selectedItems()
        if len(selected_items) != self.count_to_bottom:
            return
        self.selected_bottom_cards = [item.text() for item in selected_items]
        self.accept()


class TriggerChoiceDialog(QDialog):
    """Dialog for selecting trigger target or order."""

    def __init__(self, title: str, prompt: str, options: List[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.selected_option: Optional[str] = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(prompt))

        self.list_widget = QListWidget()
        for opt in options:
            self.list_widget.addItem(opt)
        layout.addWidget(self.list_widget)

        self.select_btn = QPushButton("Select")
        self.select_btn.clicked.connect(self.accept_choice)
        layout.addWidget(self.select_btn)

    def accept_choice(self):
        item = self.list_widget.currentItem()
        if item:
            self.selected_option = item.text()
            self.accept()


class CardChoiceDialog(QDialog):
    """Generic private CARD_CHOICE_REQUEST editor with fixed protocol semantics."""

    def __init__(self, request, parent=None):
        super().__init__(parent)
        self.request = request
        self.result = {}
        self.setWindowTitle(request.get("choice_type", "Card Choice").replace("_", " "))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(request.get("prompt", "Choose")))
        self.list_widget = QListWidget()
        choice_type = request.get("choice_type")
        options = request.get("options", [])
        if choice_type in {"SELECT_CARDS", "SELECT_TARGETS", "ORDER_CARDS"}:
            self.list_widget.setSelectionMode(
                QListWidget.MultiSelection
            )
            for option in options:
                self.list_widget.addItem(str(option))
            layout.addWidget(self.list_widget)
        elif choice_type == "COLOR":
            for option in options:
                self.list_widget.addItem(str(option))
            layout.addWidget(self.list_widget)
        self.yes_btn = QPushButton("YES / CAST / PAY")
        self.no_btn = QPushButton("NO / DECLINE")
        self.yes_btn.clicked.connect(lambda: self.accept_answer(True))
        self.no_btn.clicked.connect(lambda: self.accept_answer(False))
        layout.addWidget(self.yes_btn)
        layout.addWidget(self.no_btn)

    def accept_answer(self, affirmative):
        kind = self.request.get("choice_type")
        if kind in {"SELECT_CARDS", "SELECT_TARGETS"}:
            values = [item.text() for item in self.list_widget.selectedItems()]
            self.result = {"selected_cards" if kind == "SELECT_CARDS" else "selected_targets": values}
        elif kind == "ORDER_CARDS":
            self.result = {"ordered_cards": [item.text() for item in self.list_widget.selectedItems()]}
        elif kind == "COLOR":
            item = self.list_widget.currentItem()
            self.result = {"color": item.text() if item else ""}
        elif kind == "MADNESS_CAST":
            self.result = {"cast": affirmative}
            if affirmative:
                self.result["mana_payment"] = dict(self.request.get("required_mana", {}))
        elif kind == "PAY_MANA":
            self.result = {"pay": affirmative}
            if affirmative:
                self.result["mana_payment"] = dict(self.request.get("required_mana", {}))
        else:
            self.result = {"answer": affirmative}
        self.accept()
