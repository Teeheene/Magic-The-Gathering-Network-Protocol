import unittest
from app.shared.card_catalog import CardCatalog
from app.client.state import ClientState
from app.client.pdu_dispatcher import PduDispatcher


class TestClientCore(unittest.TestCase):
    def test_shared_card_catalog_loads(self):
        cat = CardCatalog("app/shared/card_catalog.json")
        self.assertIsNotNone(cat.get_card_data("mountain"))
        self.assertTrue(cat.is_valid_instance_id("mountain_001"))




    def test_match_start_assigns_player_id(self):
        st = ClientState("player_2")
        self.assertEqual(st.pid, "player_2")

    def test_game_state_update_replaces_authoritative_state(self):
        st = ClientState("player_1")
        st.update_game_state({"phase": "PRECOMBAT_MAIN", "turn": 1, "hand": ["mountain_001"]})
        self.assertEqual(st.phase, "PRECOMBAT_MAIN")
        self.assertEqual(st.turn, 1)

    def test_reset_for_lobby_keeps_player_id_and_clears_match_state(self):
        st = ClientState("alice")
        st.phase = "COMBAT_ATTACKERS"
        st.reset_for_lobby()
        self.assertEqual(st.pid, "alice")
        self.assertEqual(st.phase, "LOBBY")


if __name__ == "__main__":
    unittest.main()
