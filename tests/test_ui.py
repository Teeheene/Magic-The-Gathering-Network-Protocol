import unittest
from unittest.mock import patch, MagicMock

from PySide6.QtWidgets import QApplication
from app.client.qt.main_window import MainWindow
from app.client.state import ClientState

app = QApplication.instance() or QApplication([])


class TestGraphicalClientUI(unittest.TestCase):
    def setUp(self):
        self.client_state = ClientState("alice")
        self.mock_dispatcher = MagicMock()
        self.app = MainWindow(self.client_state, self.mock_dispatcher)

    def test_gui_initialization_and_title(self):
        self.assertIn("MTGNP 1.0 Client — Player: alice", self.app.windowTitle())
        self.assertIsNotNone(self.app.status_label)
        self.assertIsNotNone(self.app.life_label)

    def test_action_buttons_trigger_dispatcher_calls(self):
        self.app.pass_btn.click()
        self.mock_dispatcher.send_priority_pass.assert_called_once()

        self.app.concede_btn.click()
        self.mock_dispatcher.send_concede.assert_called_once()

    def test_ui_refresh_on_state_update(self):
        self.client_state.update_game_state({
            "phase": "PRECOMBAT_MAIN",
            "turn": 2,
            "hand": ["forest_001"],
            "life_totals": {"alice": 20, "bob": 18},
        })
        self.app.refresh_ui()
        self.assertIn("PRECOMBAT_MAIN", self.app.status_label.text())
        self.assertEqual(self.app.hand_list.count(), 1)


if __name__ == "__main__":
    unittest.main()
