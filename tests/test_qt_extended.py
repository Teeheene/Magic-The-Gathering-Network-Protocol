import unittest
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

from app.client.qt.dialogs import CardChoiceDialog
from app.client.qt.main_window import CATALOG_PATH, MainWindow
from app.client.qt.presenter import GamePresenter
from app.client.state import ClientState
from app.shared.card_catalog import CardCatalog

app = QApplication.instance() or QApplication([])


class TestQtExtendedClient(unittest.TestCase):
    def setUp(self):
        self.state = ClientState("alice")
        self.state.life_totals = {"alice": 20, "bob": 18}
        self.dispatcher = MagicMock()
        self.window = MainWindow(self.state, self.dispatcher)

    def tearDown(self):
        self.window.close()

    def test_presenter_produces_card_view_data_and_public_exile(self):
        presenter = GamePresenter(self.state, CardCatalog(CATALOG_PATH))
        card = presenter.card("forest_001", tapped=True)
        self.assertEqual(card.name, "Forest")
        self.assertTrue(card.tapped)
        self.state.update_game_state({"phase": "PRECOMBAT_MAIN", "exile": {"alice": ["rift_bolt_001"], "bob": []}})
        self.window.refresh_ui()
        self.assertEqual(self.state.exile["alice"], ["rift_bolt_001"])
        self.assertEqual(self.window.exile_list.count(), 1)

    def test_lobby_ready_uses_catalog_deck_and_dispatcher(self):
        self.window.send_ready()
        self.assertEqual(len(self.state.deck_list), 40)
        self.dispatcher.send_player_ready.assert_called_once()

    def test_generic_choice_dialog_builds_order_and_yes_no_responses(self):
        order = CardChoiceDialog({
            "choice_type": "ORDER_CARDS", "prompt": "Order", "options": ["a", "b"],
        })
        order.list_widget.item(0).setSelected(True)
        order.list_widget.item(1).setSelected(True)
        order.yes_btn.click()
        self.assertEqual(order.result, {"ordered_cards": ["a", "b"]})

        yes_no = CardChoiceDialog({"choice_type": "YES_NO", "prompt": "Search?", "options": [True, False]})
        yes_no.yes_btn.click()
        self.assertEqual(yes_no.result, {"answer": True})

    def test_priority_action_gating_and_game_board_rendering(self):
        self.state.update_game_state({
            "phase": "PRECOMBAT_MAIN", "turn": 2, "active_player": "alice",
            "priority_holder": "alice", "life_totals": {"alice": 20, "bob": 18},
            "hand": ["forest_001"], "battlefield": {"alice": [{"id": "llanowar_elves_001"}], "bob": []},
            "stack": [], "exile": {"alice": [], "bob": []},
        })
        self.window.refresh_ui()
        self.state.priority_seq_num = 1
        self.window.refresh_ui()
        self.assertTrue(self.window.pass_btn.isEnabled())
        self.assertEqual(self.window.your_battlefield_list.count(), 1)
        self.assertIn("PRECOMBAT_MAIN", self.window.status_label.text())


if __name__ == "__main__":
    unittest.main()
