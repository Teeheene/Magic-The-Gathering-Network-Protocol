from PySide6.QtWidgets import QFrame, QVBoxLayout, QLabel, QListWidget, QListWidgetItem
from PySide6.QtCore import Qt, Signal

class StackWidget(QFrame):
    stack_item_clicked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        self.setFrameShape(QFrame.StyledPanel)
        self.setStyleSheet("""
            QFrame {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 6px;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        title = QLabel("The Stack (LIFO)")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #89b4fa;")
        layout.addWidget(title)

        self.list_widget = QListWidget()
        self.list_widget.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.list_widget)

    def update_stack(self, stack_items: list):
        self.list_widget.clear()
        if not stack_items:
            empty_item = QListWidgetItem("Stack is empty")
            empty_item.setFlags(Qt.NoItemFlags)
            empty_item.setForeground(Qt.gray)
            self.list_widget.addItem(empty_item)
            return

        # Stack is ordered bottom-to-top in protocol.
        # Top-most item resolves next!
        for idx in range(len(stack_items) - 1, -1, -1):
            item = stack_items[idx]
            sid = item.get("stack_item_id") if isinstance(item, dict) else str(item)
            source = item.get("source", "Spell/Ability") if isinstance(item, dict) else str(item)
            controller = item.get("controller", "-") if isinstance(item, dict) else ""
            targets = item.get("targets", []) if isinstance(item, dict) else []

            is_top = (idx == len(stack_items) - 1)
            prefix = "NEXT RESOLVE → " if is_top else f"[{idx}] "
            target_str = f" → {', '.join(targets)}" if targets else ""

            label_text = f"{prefix}{source} ({controller}){target_str} [{sid}]"
            list_item = QListWidgetItem(label_text)
            list_item.setData(Qt.UserRole, sid)

            if is_top:
                list_item.setForeground(Qt.yellow)
            
            self.list_widget.addItem(list_item)

    def _on_item_clicked(self, item: QListWidgetItem):
        sid = item.data(Qt.UserRole)
        if sid:
            self.stack_item_clicked.emit(sid)
