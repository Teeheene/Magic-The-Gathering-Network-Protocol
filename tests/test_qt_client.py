import unittest
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from app.client.qt.dialogs import MulliganDialog, TriggerChoiceDialog
from app.client.qt.main_window import MainWindow
from app.client.state import ClientState

# Single QApplication instance for PySide6 widget tests
app = QApplication.instance() or QApplication([])


class TestQtClient(unittest.TestCase):
    def setUp(self):
        self.state = ClientState("alice")
        self.mock_dispatcher = MagicMock()

    def test_main_window_init_and_refresh(self):
        win = MainWindow(self.state, self.mock_dispatcher)
        self.assertEqual(win.windowTitle(), "MTGNP 1.0 Client — Player: alice")

        self.state.local_hand = ["mountain_001", "shock_001"]
        self.state.life_totals = {"alice": 20, "bob": 15}
        win.refresh_ui()

        self.assertIn("20", win.life_label.text())
        self.assertIn("alice", win.life_label.text())


    def test_mulligan_dialog_keep_choice(self):
        dlg = MulliganDialog(["mountain_001"], count_to_bottom=0)
        dlg.keep_btn.click()
        self.assertEqual(dlg.choice, "KEEP")

    def test_trigger_choice_dialog(self):
        dlg = TriggerChoiceDialog("Trigger Choice", "Select target:", ["target_1", "target_2"])
        dlg.list_widget.setCurrentRow(0)
        dlg.select_btn.click()
        self.assertEqual(dlg.selected_option, "target_1")


if __name__ == "__main__":
    unittest.main()
