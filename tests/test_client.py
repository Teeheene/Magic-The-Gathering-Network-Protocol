import unittest
from unittest.mock import MagicMock

from app.client.pdu_dispatcher import PduDispatcher
from app.client.state import ClientState


class TestClientStateAndRendering(unittest.TestCase):
    def setUp(self):
        self.client_state = ClientState("player_1")
        self.mock_connection = MagicMock()
        self.dispatcher = PduDispatcher(self.client_state, self.mock_connection)

    def test_authoritative_state_replacement(self):
        pdu1 = {
            "type": "GAME_STATE_UPDATE",
            "seq_num": 10,
            "state": {
                "turn": 1,
                "phase": "PRECOMBAT_MAIN",
                "life_totals": {"player_1": 20, "player_2": 20},
                "hand": {"player_1": ["shock_001"]},
            },
        }
        self.dispatcher.handle(pdu1)
        self.assertEqual(self.client_state.local_hand, ["shock_001"])
        self.assertEqual(self.client_state.latest_seq_num, 10)

        pdu2 = {
            "type": "GAME_STATE_UPDATE",
            "seq_num": 11,
            "state": {
                "turn": 1,
                "phase": "PRECOMBAT_MAIN",
                "life_totals": {"player_1": 18, "player_2": 20},
                "hand": {"player_1": ["lightning_bolt_001"]},
            },
        }
        self.dispatcher.handle(pdu2)
        self.assertEqual(self.client_state.local_hand, ["lightning_bolt_001"])
        self.assertEqual(self.client_state.latest_seq_num, 11)

    def test_opponent_hand_remains_hidden(self):
        pdu = {
            "type": "GAME_STATE_UPDATE",
            "seq_num": 5,
            "state": {
                "phase": "PRECOMBAT_MAIN",
                "hand": {"player_1": ["mountain_001", "shock_001"]},
                "hand_counts": {"player_2": 6},
            },
        }
        self.dispatcher.handle(pdu)

        self.assertEqual(self.client_state.local_hand, ["mountain_001", "shock_001"])
        self.assertEqual(self.client_state.hand_counts.get("player_2"), 6)
        self.assertNotIn("counterspell_001", self.client_state.local_hand)

    def test_stack_push_and_resolve(self):
        push_pdu = {
            "type": "STACK_PUSH",
            "seq_num": 8,
            "stack_item_id": "stk_01",
            "item_type": "SPELL",
            "source": "shock_001",
            "controller": "player_1",
            "targets": ["player_2"],
        }
        self.dispatcher.handle(push_pdu)
        self.assertEqual(len(self.client_state.stack), 1)
        self.assertEqual(self.client_state.stack[0]["stack_item_id"], "stk_01")

        resolve_pdu = {
            "type": "STACK_RESOLVE",
            "seq_num": 9,
            "stack_item_id": "stk_01",
            "result": "RESOLVED",
            "state_changes": [],
        }
        self.dispatcher.handle(resolve_pdu)
        self.assertEqual(len(self.client_state.stack), 0)

    def test_error_pdu_handling_without_crash(self):
        pdu_err = {
            "type": "ERROR",
            "seq_num": 12,
            "code": "STALE_ACTION",
            "message": "Priority token mismatch.",
            "rejected_action": {"type": "PRIORITY_PASS"},
        }
        self.dispatcher.handle(pdu_err)
        self.assertIsNotNone(self.client_state.last_error)
        self.assertEqual(self.client_state.last_error["code"], "STALE_ACTION")

    def test_gameplay_action_builders_echo_seq_num(self):
        self.client_state.priority_seq_num = 42

        self.dispatcher.send_priority_pass()
        self.mock_connection.send.assert_called_with({
            "type": "PRIORITY_PASS",
            "seq_num": 42,
        })

        self.dispatcher.send_cast_spell(
            "shock_001",
            targets=["player_2"],
            mana_payment={"R": 1},
        )
        self.mock_connection.send.assert_called_with({
            "type": "CAST_SPELL",
            "seq_num": 42,
            "card_id": "shock_001",
            "targets": ["player_2"],
            "mana_payment": {"R": 1},
        })

        self.dispatcher.send_play_land("mountain_001")
        self.mock_connection.send.assert_called_with({
            "type": "PLAY_LAND",
            "seq_num": 42,
            "card_id": "mountain_001",
        })


if __name__ == "__main__":
    unittest.main()

