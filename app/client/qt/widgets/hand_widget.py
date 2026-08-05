from PySide6.QtWidgets import QScrollArea, QWidget, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QFrame
from PySide6.QtCore import Signal, Qt
from app.shared.cards import CardCatalog

class HandCardWidget(QFrame):
    clicked = Signal(str)

    def __init__(self, card_id: str, parent=None):
        super().__init__(parent)
        self.card_id = card_id
        self.is_selected = False
        self._init_ui()

    def _init_ui(self):
        self.setFixedSize(140, 190)
        self.setFrameShape(QFrame.StyledPanel)
        self.set_selected(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)

        cat = CardCatalog.get_instance()
        defn = cat.get_definition(self.card_id)

        title_lbl = QLabel(defn.name if defn else self.card_id)
        title_lbl.setStyleSheet("font-weight: bold; font-size: 11px; color: #cdd6f4;")
        title_lbl.setWordWrap(True)
        layout.addWidget(title_lbl)

        if defn and defn.mana_cost:
            cost_str = " ".join([f"{{{k}}}:{v}" for k, v in defn.mana_cost.items()])
            cost_lbl = QLabel(cost_str)
            cost_lbl.setStyleSheet("font-size: 10px; color: #89b4fa; font-weight: bold;")
            layout.addWidget(cost_lbl)

        type_lbl = QLabel(defn.card_type if defn else "Card")
        type_lbl.setStyleSheet("font-size: 9px; color: #a6adc8; font-style: italic;")
        layout.addWidget(type_lbl)

        text_lbl = QLabel(defn.text if defn else "")
        text_lbl.setStyleSheet("font-size: 9px; color: #bac2de;")
        text_lbl.setWordWrap(True)
        layout.addWidget(text_lbl, 1)

        id_lbl = QLabel(self.card_id)
        id_lbl.setStyleSheet("font-size: 8px; color: #6c7086; font-family: Consolas;")
        layout.addWidget(id_lbl)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        if selected:
            self.setStyleSheet("""
                QFrame {
                    background-color: #45475a;
                    border: 2px solid #89b4fa;
                    border-radius: 6px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background-color: #313244;
                    border: 1px solid #45475a;
                    border-radius: 6px;
                }
                QFrame:hover {
                    background-color: #45475a;
                }
            """)

    def mousePressEvent(self, event):
        self.clicked.emit(self.card_id)
        super().mousePressEvent(event)

class HandWidget(QScrollArea):
    card_selected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.selected_card_id: str = ""
        self._init_ui()

    def _init_ui(self):
        self.setWidgetResizable(True)
        self.setFixedHeight(215)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("""
            QScrollArea {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 6px;
            }
        """)

        self.container = QWidget()
        self.layout = QHBoxLayout(self.container)
        self.layout.setContentsMargins(10, 8, 10, 8)
        self.layout.setSpacing(10)
        self.layout.setAlignment(Qt.AlignLeft)

        self.setWidget(self.container)

    def update_hand(self, card_ids: list):
        # Clear existing cards
        while self.layout.count() > 0:
            item = self.layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not card_ids:
            empty_lbl = QLabel("Your hand is empty")
            empty_lbl.setStyleSheet("color: #6c7086; font-style: italic;")
            self.layout.addWidget(empty_lbl)
            return

        for cid in card_ids:
            w = HandCardWidget(cid)
            if cid == self.selected_card_id:
                w.set_selected(True)
            w.clicked.connect(self._on_card_clicked)
            self.layout.addWidget(w)

    def _on_card_clicked(self, cid: str):
        if self.selected_card_id == cid:
            self.selected_card_id = "" # Deselect
        else:
            self.selected_card_id = cid

        # Update card visual states
        for i in range(self.layout.count()):
            w = self.layout.itemAt(i).widget()
            if isinstance(w, HandCardWidget):
                w.set_selected(w.card_id == self.selected_card_id)

        self.card_selected.emit(self.selected_card_id)
