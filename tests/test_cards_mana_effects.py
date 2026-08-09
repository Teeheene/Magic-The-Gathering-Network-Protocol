import unittest
from typing import Dict, List, Any
from tests.app_old_compat import GameState, GameStack, PriorityManager, CombatManager, CardCatalog, CardEffects



class TestCardsManaEffects(unittest.TestCase):
    def setUp(self):
        self.players = ["player_1", "player_2"]
        self.state = GameState(self.players)
        self.transport = MockTransport()
        self.seq_provider = MockSeqNumProvider()
        self.phase_mgr = MockPhaseManager(active_player="player_1", current_phase="PRECOMBAT_MAIN")
        self.stack = GameStack(self.state, self.transport, self.seq_provider)
        self.priority_mgr = PriorityManager(
            self.state, self.stack, self.phase_mgr, self.transport, self.seq_provider
        )
        self.gameplay = GameplayHandler(self.state, self.stack, self.priority_mgr, self.phase_mgr)
        self.catalog = CardCatalog.get_instance()

    def test_play_land_bypasses_stack(self):
        self.state.hands["player_1"] = ["mountain_001"]
        self.priority_mgr.open_priority_window()

        res = self.gameplay.play_land("player_1", "mountain_001")
        self.assertEqual(res["status"], "SUCCESS")
        self.assertNotIn("mountain_001", self.state.hands["player_1"])
        self.assertEqual(len(self.state.battlefield["player_1"]), 1)
        self.assertEqual(self.state.battlefield["player_1"][0]["id"], "mountain_001")
        self.assertTrue(self.state.land_played_this_turn)
        self.assertEqual(len(self.state.stack), 0) # Bypassed stack!

    def test_play_land_fails_if_already_played(self):
        self.state.hands["player_1"] = ["mountain_001", "mountain_002"]
        self.priority_mgr.open_priority_window()

        self.gameplay.play_land("player_1", "mountain_001")
        res = self.gameplay.play_land("player_1", "mountain_002")
        self.assertEqual(res["status"], "ERROR")
        self.assertEqual(res["code"], "ILLEGAL_ACTION")

    def test_land_cannot_be_cast_as_a_spell(self):
        self.state.hands["player_1"] = ["mountain_001"]
        self.priority_mgr.open_priority_window()

        res = self.gameplay.cast_spell("player_1", "mountain_001", [], {})

        self.assertEqual(res["status"], "ERROR")
        self.assertEqual(res["code"], "ILLEGAL_ACTION")
        self.assertIn("cannot be cast", res["message"])
        self.assertIn("mountain_001", self.state.hands["player_1"])
        self.assertTrue(self.stack.is_empty())

    def test_cast_spell_insufficient_mana_atomic_rollback(self):
        self.state.hands["player_1"] = ["lightning_bolt_001"]
        self.state.battlefield["player_1"] = [{"id": "mountain_001", "tapped": True}]
        self.priority_mgr.open_priority_window()

        res = self.gameplay.cast_spell("player_1", "lightning_bolt_001", ["player_2"], {"R": 1})
        self.assertEqual(res["status"], "ERROR")
        self.assertEqual(res["code"], "INSUFFICIENT_MANA")
        # State unchanged
        self.assertIn("lightning_bolt_001", self.state.hands["player_1"])
        self.assertEqual(len(self.state.stack), 0)
        self.assertTrue(self.state.battlefield["player_1"][0]["tapped"])

    def test_cast_spell_successful_payment_and_stack_push(self):
        self.state.hands["player_1"] = ["lightning_bolt_001"]
        self.state.battlefield["player_1"] = [{"id": "mountain_001", "tapped": False}]
        self.priority_mgr.open_priority_window()

        res = self.gameplay.cast_spell("player_1", "lightning_bolt_001", ["player_2"], {"R": 1})
        self.assertEqual(res["status"], "SUCCESS")
        self.assertNotIn("lightning_bolt_001", self.state.hands["player_1"])
        self.assertTrue(self.state.battlefield["player_1"][0]["tapped"])
        self.assertEqual(len(self.state.stack), 1)

    def test_spell_resolution_damage_and_graveyard_movement(self):
        self.state.hands["player_1"] = ["lightning_bolt_001"]
        self.state.battlefield["player_1"] = [{"id": "mountain_001", "tapped": False}]
        self.priority_mgr.open_priority_window()

        self.gameplay.cast_spell("player_1", "lightning_bolt_001", ["player_2"], {"R": 1})
        
        # Both pass -> resolution
        self.priority_mgr.handle_pass("player_1")
        res = self.priority_mgr.handle_pass("player_2")

        self.assertEqual(res["status"], "RESOLVED")
        self.assertEqual(self.state.life_totals["player_2"], 17) # 20 - 3 = 17
        self.assertIn("lightning_bolt_001", self.state.graveyards["player_1"]) # Instant goes to GY

    def test_creature_spell_resolution_enters_battlefield(self):
        self.state.hands["player_1"] = ["grizzly_bears_001"]
        self.state.battlefield["player_1"] = [
            {"id": "forest_001", "tapped": False},
            {"id": "forest_002", "tapped": False}
        ]
        self.priority_mgr.open_priority_window()

        res = self.gameplay.cast_spell("player_1", "grizzly_bears_001", [], {"G": 1, "Generic": 1})
        self.assertEqual(res["status"], "SUCCESS")

        self.priority_mgr.handle_pass("player_1")
        self.priority_mgr.handle_pass("player_2")

        # Creature enters battlefield
        bf = self.state.battlefield["player_1"]
        creature_perm = next((p for p in bf if p["id"] == "grizzly_bears_001"), None)
        self.assertIsNotNone(creature_perm)
        self.assertEqual(creature_perm["power"], 2)
        self.assertEqual(creature_perm["toughness"], 2)
        self.assertTrue(creature_perm["summoning_sick"])

    def test_effect_counterspell(self):
        self.state.hands["player_1"] = ["lightning_bolt_001"]
        self.state.hands["player_2"] = ["counterspell_001"]
        self.state.battlefield["player_1"] = [{"id": "mountain_001", "tapped": False}]
        self.state.battlefield["player_2"] = [
            {"id": "island_001", "tapped": False},
            {"id": "island_002", "tapped": False}
        ]
        self.priority_mgr.open_priority_window()

        # AP casts bolt
        self.gameplay.cast_spell("player_1", "lightning_bolt_001", ["player_2"], {"R": 1})
        
        # AP passes, NAP receives priority and casts Counterspell targeting bolt
        self.priority_mgr.handle_pass("player_1")
        bolt_stack_id = self.state.stack[0]["stack_item_id"]
        res_cs = self.gameplay.cast_spell("player_2", "counterspell_001", [bolt_stack_id], {"U": 2})
        self.assertEqual(res_cs["status"], "SUCCESS")

        # Both pass -> Counterspell resolves top
        self.priority_mgr.handle_pass("player_2")
        self.priority_mgr.handle_pass("player_1")

        self.assertEqual(len(self.state.stack), 0)
        self.assertIn("lightning_bolt_001", self.state.graveyards["player_1"])
        self.assertIn("counterspell_001", self.state.graveyards["player_2"])
        self.assertEqual(self.state.life_totals["player_2"], 20) # Bolt was countered!

if __name__ == "__main__":
    unittest.main()
