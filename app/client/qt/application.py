import sys
from PySide6.QtWidgets import QApplication
from app.client.controller import ClientController
from app.client.qt.main_window import MainWindow

def run_qt_app(host: str = None, port: int = None, verbose: bool = False) -> None:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    controller = ClientController(verbose=verbose)
    window = MainWindow(controller=controller, host=host, port=port)
    window.show()
    sys.exit(app.exec())
