import unittest
from typing import Dict, List, Any
from app.server.game import Game

class TransportInterface: pass
class PhaseManagerInterface: pass
class SeqNumProvider: pass

class MockTransport(TransportInterface):
    def __init__(self):
        self.sent_messages: List[tuple] = []
        self.broadcast_messages: List[Dict[str, Any]] = []

    def send_to_player(self, player_id: str, pdu: Dict[str, Any]) -> None:
        self.sent_messages.append((player_id, pdu))

    def broadcast(self, pdu: Dict[str, Any]) -> None:
        self.broadcast_messages.append(pdu)

class MockPhaseManager(PhaseManagerInterface):
    def __init__(self, active_player="player_1", current_phase="PRECOMBAT_MAIN"):
        self.active_player = active_player
        self.current_phase = current_phase
        self.phase_advanced = False
        self.land_played = False
        self.turn = 1

    def get_current_phase(self) -> str:
        return self.current_phase

    def get_active_player(self) -> str:
        return self.active_player

    def is_main_phase(self) -> bool:
        return self.current_phase in ("PRECOMBAT_MAIN", "POSTCOMBAT_MAIN")

    def advance_phase(self) -> None:
        self.phase_advanced = True

    def get_turn_number(self) -> int:
        return self.turn

    def has_land_been_played(self) -> bool:
        return self.land_played

    def mark_land_played(self) -> None:
        self.land_played = True

    def is_first_turn_first_player(self) -> bool:
        return False

class MockSeqNumProvider(SeqNumProvider):
    def __init__(self):
        self.seq = 0

    def next_seq_num(self) -> int:
        self.seq += 1
        return self.seq

class TestPriorityAndStack(unittest.TestCase):
    def setUp(self):
        self.players = ["player_1", "player_2"]
        self.state = GameState(self.players)
        self.transport = MockTransport()
        self.seq_provider = MockSeqNumProvider()
        self.phase_mgr = MockPhaseManager(active_player="player_1")
        self.stack = GameStack(self.state, self.transport, self.seq_provider)
        self.priority_mgr = PriorityManager(
            self.state, self.stack, self.phase_mgr, self.transport, self.seq_provider
        )

    def test_open_priority_window_grants_ap(self):
        self.priority_mgr.open_priority_window()
        self.assertEqual(self.state.priority_holder, "player_1")
        self.assertEqual(self.transport.broadcast_messages, [])
        self.assertEqual(len(self.transport.sent_messages), 1)
        recipient, pdu = self.transport.sent_messages[0]
        self.assertEqual(recipient, "player_1")
        self.assertEqual(pdu["type"], "PRIORITY_GRANT")
        self.assertEqual(pdu["player_id"], "player_1")

    def test_priority_pass_transfers_to_nap(self):
        self.priority_mgr.open_priority_window()
        res = self.priority_mgr.handle_pass("player_1")
        self.assertEqual(res["status"], "PASSED")
        self.assertEqual(self.state.priority_holder, "player_2")

    def test_consecutive_pass_empty_stack_advances_phase(self):
        self.priority_mgr.open_priority_window()
        self.priority_mgr.handle_pass("player_1")
        res = self.priority_mgr.handle_pass("player_2")
        self.assertEqual(res["status"], "WINDOW_CLOSED")
        self.assertTrue(self.phase_mgr.phase_advanced)

    def test_action_resets_consecutive_passes_and_retains_priority(self):
        self.priority_mgr.open_priority_window()
        self.priority_mgr.handle_pass("player_1") # 1 pass
        self.priority_mgr.handle_action("player_2") # action by player_2
        self.assertEqual(self.priority_mgr.consecutive_passes, 0)
        self.assertEqual(self.state.priority_holder, "player_2")

    def test_lifo_stack_push_and_resolution(self):
        resolved_order = []
        def effect1(item, state):
            resolved_order.append("item1")
            return [{"change_type": "DAMAGE", "target": "player_2", "amount": 3}]

        def effect2(item, state, game_stack=None):
            resolved_order.append("item2")
            import app.server.game.effects as FX
            return FX.counter_spell(item.targets[0], state, game_stack or self.stack)

        item1 = StackItem("stk_01", "SPELL", "shock_001", "player_1", ["player_2"], effect_fn=effect1)
        item2 = StackItem("stk_02", "SPELL", "counterspell_001", "player_2", ["stk_01"], effect_fn=effect2)

        self.stack.push(item1)
        self.stack.push(item2)

        self.assertEqual(len(self.state.stack), 2)
        self.assertEqual(self.state.stack[0]["stack_item_id"], "stk_01") # bottom
        self.assertEqual(self.state.stack[1]["stack_item_id"], "stk_02") # top

        # Both pass -> top item (stk_02) resolves
        self.priority_mgr.open_priority_window()
        self.priority_mgr.handle_pass("player_1")
        res = self.priority_mgr.handle_pass("player_2")

        self.assertEqual(res["status"], "RESOLVED")
        self.assertEqual(resolved_order, ["item2"])
        self.assertEqual(len(self.state.stack), 0)
        # Priority goes back to AP (player_1)
        self.assertEqual(self.state.priority_holder, "player_1")

    def test_fizzle_when_all_targets_illegal(self):
        def effect(item, state):
            return [{"change_type": "DESTROY", "target": "invalid_perm"}]

        item = StackItem("stk_01", "SPELL", "terror_001", "player_1", ["non_existent_perm"], effect_fn=effect)
        self.stack.push(item)

        self.priority_mgr.open_priority_window()
        self.priority_mgr.handle_pass("player_1")
        res = self.priority_mgr.handle_pass("player_2")

        self.assertEqual(res["status"], "RESOLVED")
        self.assertEqual(res["resolve_result"]["result"], "FIZZLE")
        self.assertEqual(len(self.state.stack), 0)

if __name__ == "__main__":
    unittest.main()
