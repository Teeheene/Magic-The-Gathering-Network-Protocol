from PySide6.QtWidgets import QMessageBox

class ErrorDialog:
    @staticmethod
    def show_error(parent, code: str, message: str):
        msg_box = QMessageBox(parent)
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setWindowTitle(f"Protocol Error - {code}")
        msg_box.setText(f"Action Rejected [{code}]")
        msg_box.setInformativeText(message)
        msg_box.exec()
