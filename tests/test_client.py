import unittest
from app.client.state import ClientState

class TestClientStateAndRendering(unittest.TestCase):
    def setUp(self):
        self.client_state = ClientState()
        self.client_state.player_id = "player_1"

    def test_authoritative_state_replacement(self):
        pdu1 = {
            "type": "GAME_STATE_UPDATE",
            "seq_num": 10,
            "state": {
                "turn": 1,
                "phase": "PRECOMBAT_MAIN",
                "life_totals": {"player_1": 20, "player_2": 20},
                "hand": {"player_1": ["shock_001"]}
            }
        }
        self.client_state.update_authoritative_state(pdu1)
        self.assertEqual(self.client_state.get_local_hand(), ["shock_001"])

        pdu2 = {
            "type": "GAME_STATE_UPDATE",
            "seq_num": 11,
            "state": {
                "turn": 1,
                "phase": "PRECOMBAT_MAIN",
                "life_totals": {"player_1": 18, "player_2": 20},
                "hand": {"player_1": ["lightning_bolt_001"]}
            }
        }
        self.client_state.update_authoritative_state(pdu2)
        self.assertEqual(self.client_state.get_local_hand(), ["lightning_bolt_001"])
        self.assertEqual(self.client_state.latest_state_seq_num, 11)

    def test_opponent_hand_remains_hidden(self):
        pdu = {
            "type": "GAME_STATE_UPDATE",
            "seq_num": 5,
            "state": {
                "hand": {"player_1": ["mountain_001", "shock_001"]},
                "hand_counts": {"player_2": 6}
            }
        }
        self.client_state.update_authoritative_state(pdu)
        rendered = self.client_state.render()

        self.assertIn("mountain_001", rendered)
        self.assertIn("'player_2': 6", rendered)
        self.assertNotIn("counterspell_001", rendered)

    def test_stack_renders_bottom_to_top(self):
        pdu = {
            "type": "GAME_STATE_UPDATE",
            "seq_num": 8,
            "state": {
                "stack": [
                    {"stack_item_id": "stk_01", "source": "shock_001", "controller": "player_1"},
                    {"stack_item_id": "stk_02", "source": "counterspell_001", "controller": "player_2"}
                ]
            }
        }
        self.client_state.update_authoritative_state(pdu)
        rendered = self.client_state.render()

        self.assertIn("[0] ID: stk_01", rendered)
        self.assertIn("[1] ID: stk_02", rendered)

    def test_error_pdu_handling_without_crash(self):
        pdu_err = {
            "type": "ERROR",
            "seq_num": 12,
            "code": "STALE_ACTION",
            "message": "Priority token mismatch."
        }
        self.client_state.update_authoritative_state(pdu_err)
        rendered = self.client_state.render()

        self.assertIn("STALE_ACTION", rendered)

    def test_gameplay_action_builders_echo_seq_num(self):
        self.client_state.last_seq_num = 42

        p_pass = self.client_state.build_priority_pass()
        self.assertEqual(p_pass, {"type": "PRIORITY_PASS", "seq_num": 42})

        p_cast = self.client_state.build_cast_spell("shock_001", ["player_2"], {"R": 1})
        self.assertEqual(p_cast["seq_num"], 42)
        self.assertEqual(p_cast["card_id"], "shock_001")

        p_land = self.client_state.build_play_land("mountain_001")
        self.assertEqual(p_land, {"type": "PLAY_LAND", "seq_num": 42, "card_id": "mountain_001"})

        p_atk = self.client_state.build_declare_attackers([{"creature_id": "goblin_guide_001", "target": "player_2"}])
        self.assertEqual(p_atk["type"], "DECLARE_ATTACKERS")
        self.assertEqual(p_atk["seq_num"], 42)

if __name__ == "__main__":
    unittest.main()
