from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QVBoxLayout, QDialog
from PySide6.QtGui import QPixmap
from app.shared.card_catalog import CardCatalog


class CardWidget(QFrame):
    clicked = Signal(str)

    def __init__(self, card, parent=None, asset_manager=None, variant="art"):
        super().__init__(parent)
        self.card = card
        self.asset_manager = asset_manager
        self._asset_base = CardCatalog.base_card_id(card.card_id)
        self.setObjectName("CardWidget")
        self.setMinimumSize(130, 170)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        self.name_label = QLabel(card.name)
        self.name_label.setWordWrap(True)
        self.name_label.setStyleSheet("font-weight:700; color:#f5f1e8;")
        layout.addWidget(self.name_label)
        self.art_label = QLabel("No artwork cached")
        self.art_label.setAlignment(Qt.AlignCenter)
        self.art_label.setMinimumHeight(72)
        self.art_label.setStyleSheet("background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #34495e,stop:1 #17212b); color:#bdc7d3; border-radius:4px;")
        layout.addWidget(self.art_label)
        layout.addWidget(QLabel(card.mana_cost if isinstance(card.mana_cost, str) else str(card.mana_cost)))
        type_label = QLabel(card.card_type)
        type_label.setStyleSheet("color:#b9c0cc;")
        layout.addWidget(type_label)
        if card.power_toughness:
            layout.addWidget(QLabel(card.power_toughness, alignment=Qt.AlignRight))
        if card.tapped:
            layout.addWidget(QLabel("TAPPED", alignment=Qt.AlignCenter))
        self.setStyleSheet("QFrame#CardWidget { background:#25313a; border:1px solid #596775; border-radius:8px; }")
        if asset_manager:
            asset_manager.image_ready.connect(self._on_image_ready)
            asset_manager.request(card.card_id, variant)

    def _on_image_ready(self, base_id, variant, pixmap):
        if base_id != self._asset_base or variant != "art" or self.card is None: return
        self.art_label.setPixmap(pixmap.scaled(self.art_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.art_label.setText("")

    def mousePressEvent(self, event):
        self.clicked.emit(self.card.card_id)
        super().mousePressEvent(event)


class CardInspector(QDialog):
    """Large preview that never reveals identities absent from the supplied card."""
    def __init__(self, card, asset_manager=None, parent=None):
        super().__init__(parent)
        self.card = card; self.asset_manager = asset_manager
        self._full_failed = False; self._full_ready = False
        self.setWindowTitle(card.name); self.resize(420, 600)
        layout = QVBoxLayout(self)
        self.image = QLabel("No artwork cached"); self.image.setAlignment(Qt.AlignCenter)
        self.image.setMinimumSize(300, 400); layout.addWidget(self.image)
        layout.addWidget(QLabel(f"{card.name}\n{card.mana_cost}\n{card.card_type}\n{getattr(card, 'rules_text', getattr(card, 'text', ''))}"))
        if asset_manager:
            asset_manager.image_ready.connect(self._on_image)
            asset_manager.image_failed.connect(self._on_failed)
            asset_manager.request(card.card_id, "full")

    def _on_image(self, base_id, variant, pixmap):
        if base_id != CardCatalog.base_card_id(self.card.card_id): return
        if variant == "full": self._full_ready = True
        if variant == "art" and not self._full_failed: return
        self.image.setPixmap(pixmap.scaled(self.image.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.image.setText("")

    def _on_failed(self, base_id, variant):
        if base_id == CardCatalog.base_card_id(self.card.card_id) and variant == "full" and not self._full_ready:
            self._full_failed = True
            self.asset_manager.request(self.card.card_id, "art")


class ZoneWidget(QFrame):
    card_clicked = Signal(str)

    def __init__(self, title, parent=None, asset_manager=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight:700; color:#e3b56a;")
        self.layout.addWidget(self.title)
        self.cards_layout = QVBoxLayout()
        self.layout.addLayout(self.cards_layout)
        self.asset_manager = asset_manager

    def set_cards(self, cards):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for card in cards:
            widget = CardWidget(card, asset_manager=self.asset_manager)
            widget.clicked.connect(self.card_clicked)
            self.cards_layout.addWidget(widget)

    def count(self):
        return self.cards_layout.count()

    def clear(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()

    def addItem(self, text):
        # Compatibility no-op for legacy callers; production rendering uses CardWidget.
        return None

    def selected_ids(self):
        return [w.card.card_id for w in self.findChildren(CardWidget) if w.property("selected")]

    def currentItem(self):
        cards = self.findChildren(CardWidget)
        if not cards: return None
        return type("CardItem", (), {"text": lambda self: cards[0].card.card_id})()
