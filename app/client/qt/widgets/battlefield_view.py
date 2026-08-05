from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsLineItem
from PySide6.QtGui import QPen, QColor, QPainter
from PySide6.QtCore import Qt, Signal, QRectF
from app.client.qt.widgets.card_item import CardGraphicsItem

class BattlefieldView(QGraphicsView):
    permanent_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.setScene(self.scene)

        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.NoDrag)
        self.setStyleSheet("""
            QGraphicsView {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 6px;
            }
        """)

        self.card_items: dict[str, CardGraphicsItem] = {}

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.scene.setSceneRect(0, 0, max(800, self.width() - 10), max(500, self.height() - 10))
        self._reposition_divider()

    def _reposition_divider(self):
        w = self.scene.width()
        h = self.scene.height()
        mid_y = h / 2

        for item in self.scene.items():
            if isinstance(item, QGraphicsLineItem):
                self.scene.removeItem(item)

        line = self.scene.addLine(0, mid_y, w, mid_y, QPen(QColor("#45475a"), 2, Qt.DashLine))
        line.setZValue(-10)

    def update_battlefield(self, battlefield_data: dict, local_player_id: str):
        self.scene.clear()
        self.card_items.clear()
        self._reposition_divider()

        w = self.scene.width()
        h = self.scene.height()
        mid_y = h / 2

        local_p = local_player_id or "player_1"
        opp_p = [p for p in battlefield_data.keys() if p != local_p]
        opp_id = opp_p[0] if opp_p else ("player_2" if local_p == "player_1" else "player_1")

        opp_perms = battlefield_data.get(opp_id, [])
        local_perms = battlefield_data.get(local_p, [])

        # Render Opponent Permanents Top Area
        self._render_zone_perms(opp_perms, y_offset=20, start_x=20)

        # Render Local Permanents Bottom Area
        self._render_zone_perms(local_perms, y_offset=mid_y + 20, start_x=20)

    def _render_zone_perms(self, perms: list, y_offset: float, start_x: float):
        x = start_x
        padding = 150
        for p in perms:
            if isinstance(p, dict):
                cid = p.get("id")
                tapped = p.get("tapped", False)
                dmg = p.get("damage", 0)
                pow_val = p.get("power")
                tou_val = p.get("toughness")
                sick = p.get("summoning_sick", False)
            else:
                cid = str(p)
                tapped = False
                dmg = 0
                pow_val = None
                tou_val = None
                sick = False

            if not cid:
                continue

            item = CardGraphicsItem(
                card_id=cid,
                is_tapped=tapped,
                damage=dmg,
                power=pow_val,
                toughness=tou_val,
                summoning_sick=sick
            )
            item.setPos(x, y_offset)
            item.signals.clicked.connect(self._on_item_clicked)
            self.scene.addItem(item)
            self.card_items[cid] = item
            x += padding

    def _on_item_clicked(self, cid: str):
        self.permanent_clicked.emit(cid)
