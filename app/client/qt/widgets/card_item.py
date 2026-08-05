from PySide6.QtWidgets import QGraphicsItem, QStyleOptionGraphicsItem, QWidget
from PySide6.QtGui import QPainter, QColor, QFont, QPen, QBrush
from PySide6.QtCore import QRectF, Qt, Signal, QObject
from app.shared.cards import CardCatalog

class CardGraphicsItemSignals(QObject):
    clicked = Signal(str)

class CardGraphicsItem(QGraphicsItem):
    WIDTH = 135
    HEIGHT = 190

    def __init__(self, card_id: str, is_tapped: bool = False, damage: int = 0, power: int = None, toughness: int = None, summoning_sick: bool = False, parent=None):
        super().__init__(parent)
        self.card_id = card_id
        self.is_tapped = is_tapped
        self.damage = damage
        self.power = power
        self.toughness = toughness
        self.summoning_sick = summoning_sick
        
        self.is_selected = False
        self.is_highlighted_target = False
        self.is_attacking = False
        self.is_blocking = False
        self.blocking_target = ""

        self.signals = CardGraphicsItemSignals()

        self.catalog = CardCatalog.get_instance()
        self.definition = self.catalog.get_definition(card_id)

        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setTransformOriginPoint(self.WIDTH / 2, self.HEIGHT / 2)

        if self.is_tapped:
            self.setRotation(90)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self.WIDTH, self.HEIGHT)

    def mousePressEvent(self, event):
        self.signals.clicked.emit(self.card_id)
        super().mousePressEvent(event)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: QWidget = None):
        painter.setRenderHint(QPainter.Antialiasing)

        # Border & Selection Highlighting
        border_pen = QPen(QColor("#45475a"), 2)
        bg_color = QColor("#313244")

        if self.is_selected:
            border_pen = QPen(QColor("#89b4fa"), 3)
            bg_color = QColor("#45475a")
        elif self.is_highlighted_target:
            border_pen = QPen(QColor("#a6e3a1"), 3)
            bg_color = QColor("#313244")
        elif self.is_attacking:
            border_pen = QPen(QColor("#f38ba8"), 3)
        elif self.is_blocking:
            border_pen = QPen(QColor("#f9e2af"), 3)

        painter.setPen(border_pen)
        painter.setBrush(QBrush(bg_color))
        painter.drawRoundedRect(self.boundingRect(), 8, 8)

        # Card Title Bar & Mana Cost
        title = self.definition.name if self.definition else self.card_id
        cost_str = ""
        if self.definition and self.definition.mana_cost:
            cost_str = " ".join([f"{{{k}}}:{v}" for k, v in self.definition.mana_cost.items()])

        painter.setFont(QFont("Segoe UI", 10, QFont.Bold))
        painter.setPen(QColor("#cdd6f4"))
        painter.drawText(QRectF(8, 8, self.WIDTH - 16, 20), Qt.AlignLeft | Qt.AlignVCenter, title)

        if cost_str:
            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.setPen(QColor("#89b4fa"))
            painter.drawText(QRectF(8, 8, self.WIDTH - 16, 20), Qt.AlignRight | Qt.AlignVCenter, cost_str)

        # Card Type Line
        type_str = self.definition.card_type if self.definition else "Card"
        if self.definition and self.definition.subtype:
            type_str += f" - {self.definition.subtype}"
        painter.setFont(QFont("Segoe UI", 8, QFont.StyleItalic))
        painter.setPen(QColor("#a6adc8"))
        painter.drawText(QRectF(8, 30, self.WIDTH - 16, 16), Qt.AlignLeft | Qt.AlignVCenter, type_str)

        # Divider line
        painter.setPen(QPen(QColor("#45475a"), 1))
        painter.drawLine(8, 48, self.WIDTH - 8, 48)

        # Text Box
        text_body = self.definition.text if self.definition else ""
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#cdd6f4"))
        painter.drawText(QRectF(8, 52, self.WIDTH - 16, 95), Qt.TextWordWrap | Qt.AlignLeft, text_body)

        # Card Protocol ID Footer
        painter.setFont(QFont("Consolas", 7))
        painter.setPen(QColor("#6c7086"))
        painter.drawText(QRectF(8, self.HEIGHT - 22, self.WIDTH - 16, 14), Qt.AlignLeft, self.card_id)

        # Creature P/T Badge & Status Badges
        if self.power is not None and self.toughness is not None:
            pt_box = QRectF(self.WIDTH - 45, self.HEIGHT - 26, 38, 20)
            painter.setPen(QPen(QColor("#89b4fa"), 1))
            painter.setBrush(QBrush(QColor("#181825")))
            painter.drawRoundedRect(pt_box, 4, 4)

            painter.setFont(QFont("Segoe UI", 9, QFont.Bold))
            painter.setPen(QColor("#a6e3a1") if self.damage > 0 else QColor("#cdd6f4"))
            painter.drawText(pt_box, Qt.AlignCenter, f"{self.power}/{self.toughness}")

        # Damage Badge
        if self.damage > 0:
            dmg_box = QRectF(8, self.HEIGHT - 26, 45, 18)
            painter.setPen(QPen(QColor("#f38ba8"), 1))
            painter.setBrush(QBrush(QColor("#313244")))
            painter.drawRoundedRect(dmg_box, 4, 4)
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(QColor("#f38ba8"))
            painter.drawText(dmg_box, Qt.AlignCenter, f"Dmg: {self.damage}")

        # Summoning Sick Badge
        if self.summoning_sick:
            sick_box = QRectF(self.WIDTH - 24, 30, 16, 16)
            painter.setPen(QPen(QColor("#f9e2af"), 1))
            painter.setBrush(QBrush(QColor("#1e1e2e")))
            painter.drawEllipse(sick_box)
            painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
            painter.setPen(QColor("#f9e2af"))
            painter.drawText(sick_box, Qt.AlignCenter, "z")
