from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout


class CardWidget(QFrame):
    clicked = Signal(str)

    def __init__(self, card, parent=None):
        super().__init__(parent)
        self.card = card
        self.setObjectName("CardWidget")
        self.setMinimumSize(130, 170)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        self.name_label = QLabel(card.name)
        self.name_label.setWordWrap(True)
        self.name_label.setStyleSheet("font-weight:700; color:#f5f1e8;")
        layout.addWidget(self.name_label)
        layout.addWidget(QLabel(card.mana_cost))
        type_label = QLabel(card.card_type)
        type_label.setStyleSheet("color:#b9c0cc;")
        layout.addWidget(type_label)
        if card.power_toughness:
            layout.addWidget(QLabel(card.power_toughness, alignment=Qt.AlignRight))
        if card.tapped:
            layout.addWidget(QLabel("TAPPED", alignment=Qt.AlignCenter))
        self.setStyleSheet("QFrame#CardWidget { background:#25313a; border:1px solid #596775; border-radius:8px; }")

    def mousePressEvent(self, event):
        self.clicked.emit(self.card.card_id)
        super().mousePressEvent(event)


class ZoneWidget(QFrame):
    card_clicked = Signal(str)

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight:700; color:#e3b56a;")
        self.layout.addWidget(self.title)
        self.cards_layout = QVBoxLayout()
        self.layout.addLayout(self.cards_layout)

    def set_cards(self, cards):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for card in cards:
            widget = CardWidget(card)
            widget.clicked.connect(self.card_clicked)
            self.cards_layout.addWidget(widget)
