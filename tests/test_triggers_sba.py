import unittest
from typing import Dict, List, Any
from app.server.game.game_state import GameState
from app.server.game.stack import GameStack
from app.server.game.events import GameEvent
from app.server.game.triggers import TriggerManager
from app.server.game.sba import StateBasedActions
from tests.test_priority_stack import MockTransport, MockSeqNumProvider

class TestTriggersAndSBA(unittest.TestCase):
    def setUp(self):
        self.players = ["player_1", "player_2"]
        self.state = GameState(self.players)
        self.transport = MockTransport()
        self.seq_provider = MockSeqNumProvider()
        self.stack = GameStack(self.state, self.transport, self.seq_provider)
        self.trigger_mgr = TriggerManager(self.state, self.stack, self.transport, self.seq_provider)

    def test_goblin_guide_attack_trigger_detection(self):
        self.state.battlefield["player_1"] = [{"id": "goblin_guide_001", "tapped": True}]
        evt = GameEvent("attacker_declared", {"creature_id": "goblin_guide_001"})
        
        detected = self.trigger_mgr.detect_triggers_for_event(evt)
        self.assertEqual(len(detected), 1)
        self.assertEqual(detected[0].source_id, "goblin_guide_001")

        # Place on stack
        self.trigger_mgr.place_pending_triggers_on_stack("player_1", "player_2")
        self.assertEqual(len(self.state.stack), 1)
        self.assertEqual(self.state.stack[0]["source"], "goblin_guide_001")

    def test_ap_nap_trigger_ordering(self):
        # AP (player_1) and NAP (player_2) both trigger
        evt1 = GameEvent("permanent_entered", {"card_id": "gray_merchant_001", "controller": "player_1"})
        evt2 = GameEvent("permanent_entered", {"card_id": "gray_merchant_002", "controller": "player_2"})

        self.trigger_mgr.detect_triggers_for_event(evt1)
        self.trigger_mgr.detect_triggers_for_event(evt2)

        self.trigger_mgr.place_pending_triggers_on_stack("player_1", "player_2")

        # Stack LIFO: AP (player_1) on bottom index 0, NAP (player_2) on top index 1
        self.assertEqual(len(self.state.stack), 2)
        self.assertEqual(self.state.stack[0]["controller"], "player_1") # Bottom (resolves last)
        self.assertEqual(self.state.stack[1]["controller"], "player_2") # Top (resolves first)

    def test_sba_zero_toughness_creature_dies(self):
        self.state.battlefield["player_1"] = [
            {"id": "grizzly_bears_001", "power": 2, "toughness": 0, "damage": 0}
        ]
        changes, events, game_over = StateBasedActions.check_and_apply(self.state)

        self.assertEqual(len(self.state.battlefield["player_1"]), 0)
        self.assertIn("grizzly_bears_001", self.state.graveyards["player_1"])
        self.assertIsNone(game_over)

    def test_sba_lethal_damage_creature_destroyed(self):
        self.state.battlefield["player_2"] = [
            {"id": "grizzly_bears_002", "power": 2, "toughness": 2, "damage": 2}
        ]
        changes, events, game_over = StateBasedActions.check_and_apply(self.state)

        self.assertEqual(len(self.state.battlefield["player_2"]), 0)
        self.assertIn("grizzly_bears_002", self.state.graveyards["player_2"])
        self.assertIsNone(game_over)

    def test_sba_zero_life_game_over(self):
        self.state.life_totals["player_2"] = 0
        changes, events, game_over = StateBasedActions.check_and_apply(self.state)

        self.assertIsNotNone(game_over)
        self.assertEqual(game_over["winner_id"], "player_1")
        self.assertEqual(game_over["loser_id"], "player_2")
        self.assertEqual(game_over["reason"], "LIFE_ZERO")

    def test_sba_simultaneous_zero_life_ap_loses(self):
        self.state.active_player = "player_1"
        self.state.life_totals["player_1"] = 0
        self.state.life_totals["player_2"] = 0

        changes, events, game_over = StateBasedActions.check_and_apply(self.state)

        self.assertIsNotNone(game_over)
        self.assertEqual(game_over["loser_id"], "player_1") # AP loses
        self.assertEqual(game_over["winner_id"], "player_2") # NAP wins

if __name__ == "__main__":
    unittest.main()
