from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFormLayout, QGroupBox
)
from PySide6.QtCore import Signal, Qt

class ConnectionView(QWidget):
    connect_requested = Signal(str, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setAlignment(Qt.AlignCenter)

        box = QGroupBox("Connect to MTGNP Server")
        box.setFixedWidth(400)
        box_layout = QVBoxLayout(box)

        form_layout = QFormLayout()
        
        self.host_input = QLineEdit("127.0.0.1")
        self.port_input = QLineEdit("4444")
        
        form_layout.addRow("Server Host:", self.host_input)
        form_layout.addRow("Server Port:", self.port_input)
        box_layout.addLayout(form_layout)

        self.status_lbl = QLabel("Status: Disconnected")
        self.status_lbl.setStyleSheet("color: #a6adc8;")
        box_layout.addWidget(self.status_lbl)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.setObjectName("btn_primary")
        self.btn_connect.clicked.connect(self._on_connect_clicked)
        box_layout.addWidget(self.btn_connect)

        main_layout.addWidget(box)

    def set_status(self, text: str, is_error: bool = False):
        self.status_lbl.setText(f"Status: {text}")
        if is_error:
            self.status_lbl.setStyleSheet("color: #f38ba8;")
        else:
            self.status_lbl.setStyleSheet("color: #a6adc8;")

    def _on_connect_clicked(self):
        host = self.host_input.text().strip() or "127.0.0.1"
        try:
            port = int(self.port_input.text().strip() or "4444")
        except ValueError:
            self.set_status("Invalid port number", is_error=True)
            return

        self.set_status("Connecting...")
        self.btn_connect.setEnabled(False)
        self.connect_requested.emit(host, port)
