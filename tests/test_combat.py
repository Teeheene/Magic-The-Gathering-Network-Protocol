import unittest
from typing import Dict, List, Any
from tests.app_old_compat import GameState, CombatManager, CardCatalog

from tests.test_priority_stack import MockTransport, MockSeqNumProvider

class TestCombatSystem(unittest.TestCase):
    def setUp(self):
        self.players = ["player_1", "player_2"]
        self.state = GameState(self.players)
        self.state.active_player = "player_1"
        self.transport = MockTransport()
        self.seq_provider = MockSeqNumProvider()
        self.combat = CombatManager(self.state, self.transport, self.seq_provider)
        self.catalog = CardCatalog.get_instance()

    def test_empty_attackers_declaration(self):
        valid, msg = self.combat.validate_and_declare_attackers("player_1", [])
        self.assertTrue(valid)
        self.assertEqual(len(self.combat.attackers), 0)

    def test_summoning_sickness_rejection_and_haste_override(self):
        self.state.battlefield["player_1"] = [
            {"id": "grizzly_bears_001", "power": 2, "toughness": 2, "tapped": False, "summoning_sick": True},
            {"id": "goblin_guide_001", "power": 2, "toughness": 2, "tapped": False, "summoning_sick": True}
        ]

        # Grizzly bears has summoning sickness and no haste -> REJECTED
        valid, msg = self.combat.validate_and_declare_attackers("player_1", [{"creature_id": "grizzly_bears_001", "target": "player_2"}])
        self.assertFalse(valid)

        # Goblin guide has haste -> ACCEPTED
        valid, msg = self.combat.validate_and_declare_attackers("player_1", [{"creature_id": "goblin_guide_001", "target": "player_2"}])
        self.assertTrue(valid)

    def test_tapped_attacker_rejection_and_vigilance_prevents_tap(self):
        self.state.battlefield["player_1"] = [
            {"id": "serra_angel_001", "power": 4, "toughness": 4, "tapped": False, "summoning_sick": False},
            {"id": "savannah_lions_001", "power": 2, "toughness": 1, "tapped": True, "summoning_sick": False}
        ]

        # Savannah lions is tapped -> REJECTED
        valid, msg = self.combat.validate_and_declare_attackers("player_1", [{"creature_id": "savannah_lions_001", "target": "player_2"}])
        self.assertFalse(valid)

        # Serra angel has vigilance -> ACCEPTED and stays UNTAPPED
        valid, msg = self.combat.validate_and_declare_attackers("player_1", [{"creature_id": "serra_angel_001", "target": "player_2"}])
        self.assertTrue(valid)
        self.assertFalse(self.state.battlefield["player_1"][0]["tapped"])

    def test_defender_rejection(self):
        self.state.battlefield["player_1"] = [
            {"id": "wall_of_stone_001", "power": 0, "toughness": 8, "tapped": False, "summoning_sick": False}
        ]
        valid, msg = self.combat.validate_and_declare_attackers("player_1", [{"creature_id": "wall_of_stone_001", "target": "player_2"}])
        self.assertFalse(valid)

    def test_blocker_validation_and_flying_restriction(self):
        self.state.battlefield["player_1"] = [
            {"id": "air_elemental_001", "power": 4, "toughness": 4, "tapped": False, "summoning_sick": False}
        ]
        self.state.battlefield["player_2"] = [
            {"id": "grizzly_bears_001", "power": 2, "toughness": 2, "tapped": False, "summoning_sick": False}
        ]

        # Declare flying attacker
        self.combat.validate_and_declare_attackers("player_1", [{"creature_id": "air_elemental_001", "target": "player_2"}])

        # Non-flying blocker attempts to block flying attacker -> REJECTED
        valid, msg = self.combat.validate_and_declare_blockers("player_2", [{"creature_id": "grizzly_bears_001", "blocking_id": "air_elemental_001"}])
        self.assertFalse(valid)

    def test_unblocked_damage_to_player(self):
        self.state.battlefield["player_1"] = [
            {"id": "grizzly_bears_001", "power": 2, "toughness": 2, "tapped": False, "summoning_sick": False}
        ]
        self.combat.validate_and_declare_attackers("player_1", [{"creature_id": "grizzly_bears_001", "target": "player_2"}])

        pdu = self.combat.resolve_combat_damage(is_first_strike_step=False)
        self.assertEqual(self.state.life_totals["player_2"], 18) # 20 - 2 = 18
        self.assertEqual(len(pdu["damage_events"]), 1)
        self.assertEqual(pdu["damage_events"][0]["amount"], 2)

    def test_no_trample_overflow_damage(self):
        # Reckless Wurm (power 4) blocked by Grizzly Bears (toughness 2). No trample overflow!
        self.state.battlefield["player_1"] = [
            {"id": "reckless_wurm_001", "power": 4, "toughness": 4, "tapped": False, "summoning_sick": False}
        ]
        self.state.battlefield["player_2"] = [
            {"id": "grizzly_bears_001", "power": 2, "toughness": 2, "tapped": False, "summoning_sick": False}
        ]

        self.combat.validate_and_declare_attackers("player_1", [{"creature_id": "reckless_wurm_001", "target": "player_2"}])
        self.combat.validate_and_declare_blockers("player_2", [{"creature_id": "grizzly_bears_001", "blocking_id": "reckless_wurm_001"}])

        pdu = self.combat.resolve_combat_damage(is_first_strike_step=False)

        self.assertEqual(self.state.life_totals["player_2"], 20) # 0 damage to player!
        bears_perm = self.state.battlefield["player_2"][0]
        self.assertEqual(bears_perm["damage"], 4) # Full 4 damage assigned to blocker

    def test_first_strike_damage_step(self):
        self.state.battlefield["player_1"] = [
            {"id": "white_knight_001", "power": 2, "toughness": 2, "tapped": False, "summoning_sick": False} # First strike!
        ]
        self.state.battlefield["player_2"] = [
            {"id": "grizzly_bears_001", "power": 2, "toughness": 2, "tapped": False, "summoning_sick": False}
        ]

        self.combat.validate_and_declare_attackers("player_1", [{"creature_id": "white_knight_001", "target": "player_2"}])
        self.combat.validate_and_declare_blockers("player_2", [{"creature_id": "grizzly_bears_001", "blocking_id": "white_knight_001"}])

        # First strike step: White Knight deals 2 damage to Grizzly Bears
        pdu_fs = self.combat.resolve_combat_damage(is_first_strike_step=True)
        self.assertEqual(len(pdu_fs["damage_events"]), 1)
        self.assertEqual(pdu_fs["damage_events"][0]["source"], "white_knight_001")

        # Regular step: White Knight does NOT deal damage a second time
        pdu_reg = self.combat.resolve_combat_damage(is_first_strike_step=False)
        fs_sources = [d["source"] for d in pdu_reg["damage_events"]]
        self.assertNotIn("white_knight_001", fs_sources)

    def test_last_blocker_receives_all_remaining_damage(self):
        self.state.battlefield["player_1"] = [
            {"id": "reckless_wurm_001", "power": 4, "toughness": 4, "tapped": False, "summoning_sick": False}
        ]
        self.state.battlefield["player_2"] = [
            {"id": "savannah_lions_001", "power": 2, "toughness": 1, "damage": 0, "tapped": False},
            {"id": "grizzly_bears_001", "power": 2, "toughness": 2, "damage": 0, "tapped": False},
        ]
        self.combat.validate_and_declare_attackers("player_1", [{"creature_id": "reckless_wurm_001", "target": "player_2"}])
        self.combat.validate_and_declare_blockers("player_2", [
            {"creature_id": "savannah_lions_001", "blocking_id": "reckless_wurm_001"},
            {"creature_id": "grizzly_bears_001", "blocking_id": "reckless_wurm_001"},
        ])
        self.combat.set_damage_order("reckless_wurm_001", ["savannah_lions_001", "grizzly_bears_001"])
        self.combat.resolve_combat_damage()
        self.assertEqual(self.state.get_permanent("savannah_lions_001")["damage"], 1)
        self.assertEqual(self.state.get_permanent("grizzly_bears_001")["damage"], 3)

if __name__ == "__main__":
    unittest.main()
