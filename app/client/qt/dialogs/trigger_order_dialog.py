from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton
)

class TriggerOrderDialog(QDialog):
    def __init__(self, trigger_ids: list, parent=None):
        super().__init__(parent)
        self.trigger_ids = list(trigger_ids)
        self.ordered_triggers = []

        self.setWindowTitle("Order Simultaneous Triggers")
        self.setMinimumWidth(400)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel("Reorder Simultaneous Triggers")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #89b4fa;")
        layout.addWidget(title)

        exp = QLabel("Note: Triggers put on stack last will resolve first!")
        exp.setStyleSheet("color: #f9e2af;")
        layout.addWidget(exp)

        h_layout = QHBoxLayout()
        self.list_widget = QListWidget()
        for trg in self.trigger_ids:
            self.list_widget.addItem(trg)
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

        self.btn_confirm = QPushButton("Confirm Trigger Order")
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
        self.ordered_triggers = [self.list_widget.item(i).text() for i in range(self.list_widget.count())]
        self.accept()
