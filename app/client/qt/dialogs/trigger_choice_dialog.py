from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QMessageBox
)

class TriggerChoiceDialog(QDialog):
    def __init__(self, pdu: dict, parent=None):
        super().__init__(parent)
        self.pdu = pdu
        self.accept_choice = False
        self.selected_targets = []

        self.setWindowTitle("Triggered Ability Choice")
        self.setMinimumWidth(380)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        trg_id = self.pdu.get("trigger_id", "")
        effect_sum = self.pdu.get("effect_summary", self.pdu.get("summary", "Triggered Ability"))
        req_target = self.pdu.get("requires_target", False)
        legal_targets = self.pdu.get("legal_targets", [])

        title = QLabel(f"Triggered Ability ({trg_id})")
        title.setStyleSheet("font-size: 14px; font-weight: bold; color: #89b4fa;")
        layout.addWidget(title)

        body = QLabel(effect_sum)
        body.setStyleSheet("color: #cdd6f4;")
        body.setWordWrap(True)
        layout.addWidget(body)

        self.target_widget = None
        if req_target and legal_targets:
            t_lbl = QLabel("Select Legal Target:")
            t_lbl.setStyleSheet("font-weight: bold; color: #a6e3a1; margin-top: 8px;")
            layout.addWidget(t_lbl)

            self.target_widget = QListWidget()
            for target in legal_targets:
                self.target_widget.addItem(target)
            layout.addWidget(self.target_widget)

        btn_layout = QHBoxLayout()
        self.btn_accept = QPushButton("Accept Trigger")
        self.btn_accept.setObjectName("btn_success")
        self.btn_accept.clicked.connect(self._on_accept)

        self.btn_decline = QPushButton("Decline")
        self.btn_decline.setObjectName("btn_danger")
        self.btn_decline.clicked.connect(self._on_decline)

        btn_layout.addWidget(self.btn_accept)
        btn_layout.addWidget(self.btn_decline)
        layout.addLayout(btn_layout)

    def _on_accept(self):
        if self.target_widget:
            selected = self.target_widget.selectedItems()
            if not selected:
                QMessageBox.warning(self, "Target Required", "Please select a legal target for this trigger.")
                return
            self.selected_targets = [item.text() for item in selected]

        self.accept_choice = True
        self.accept()

    def _on_decline(self):
        self.accept_choice = False
        self.selected_targets = []
        self.accept()
