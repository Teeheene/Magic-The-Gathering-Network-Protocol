import unittest
from app.shared.cards import CardCatalog, CardDefinition
from app.client.state import ClientState, build_default_development_deck, validate_deck
from app.server.game.game_state import GameState
from app.server.game.stack import GameStack
from app.server.game.priority import PriorityManager
from app.server.game.gameplay_handler import GameplayHandler
from app.server.game.events import EventBus
from app.server.game.triggers import TriggerManager
from app.server.game.combat import CombatManager, CombatOrchestrator
from tests.test_priority_stack import MockTransport, MockPhaseManager, MockSeqNumProvider

class TestGameplayRegressions(unittest.TestCase):
    def setUp(self):
        self.players = ["player_1", "player_2"]
        self.game_state = GameState(self.players)
        self.game_state.active_player = "player_1"
        self.game_state.phase = "PRECOMBAT_MAIN"
        
        self.transport = MockTransport()
        self.seq_num_provider = MockSeqNumProvider()
        self.phase_manager = MockPhaseManager(active_player="player_1", current_phase="PRECOMBAT_MAIN")
        self.event_bus = EventBus()
        self.game_stack = GameStack(self.game_state, self.transport, self.seq_num_provider)
        self.priority_manager = PriorityManager(self.game_state, self.game_stack, self.phase_manager, self.transport, self.seq_num_provider)
        self.gameplay_handler = GameplayHandler(self.game_state, self.game_stack, self.priority_manager, self.phase_manager, self.event_bus)
        self.trigger_manager = TriggerManager(self.game_state, self.game_stack, self.transport, self.seq_num_provider, self.event_bus)

    def test_counterspell_production_path(self):
        self.game_state.hands["player_1"] = ["lightning_bolt_001"]
        self.game_state.hands["player_2"] = ["counterspell_001"]
        self.game_state.battlefield["player_1"] = [{"id": "mountain_001", "tapped": False}]
        self.game_state.battlefield["player_2"] = [{"id": "island_001", "tapped": False}, {"id": "island_002", "tapped": False}]

        self.priority_manager.open_priority_window()

        # player_1 casts Lightning Bolt
        res1 = self.gameplay_handler.cast_spell("player_1", "lightning_bolt_001", ["player_2"], {"R": 1})
        self.assertEqual(res1["status"], "SUCCESS", res1.get("message"))
        bolt_stk_id = res1["stack_item_id"]

        # Player 1 passes priority to Player 2
        self.priority_manager.handle_pass("player_1")

        # Priority passes to player_2
        # player_2 casts Counterspell targeting Lightning Bolt
        res2 = self.gameplay_handler.cast_spell("player_2", "counterspell_001", [bolt_stk_id], {"U": 2})
        self.assertEqual(res2["status"], "SUCCESS", res2.get("message"))

        # Both pass -> Counterspell resolves
        self.priority_manager.handle_pass("player_2")
        self.priority_manager.handle_pass("player_1")

        # Verify Lightning Bolt was counterspelled and removed from stack
        self.assertTrue(self.game_stack.is_empty())
        self.assertEqual(len(self.game_state.stack), 0)

        # Both pass again -> Stack is empty, phase can advance
        self.priority_manager.handle_pass("player_1")
        self.priority_manager.handle_pass("player_2")

        self.assertEqual(self.game_state.life_totals["player_2"], 20)
        self.assertIn("lightning_bolt_001", self.game_state.graveyards["player_1"])
        self.assertIn("counterspell_001", self.game_state.graveyards["player_2"])
        self.assertEqual(self.game_state.graveyards["player_1"].count("lightning_bolt_001"), 1)
        self.assertEqual(self.game_state.graveyards["player_2"].count("counterspell_001"), 1)

    def test_gray_merchant_end_to_end(self):
        self.game_state.hands["player_1"] = ["gray_merchant_001"]
        self.game_state.battlefield["player_1"] = [{"id": f"swamp_{i:03d}", "tapped": False} for i in range(1, 6)]
        self.priority_manager.open_priority_window()

        # Cast Gray Merchant
        res = self.gameplay_handler.cast_spell("player_1", "gray_merchant_001", [], {"B": 5})
        self.assertEqual(res["status"], "SUCCESS", res.get("message"))

        # Priority pass -> Creature spell resolves and enters battlefield ONCE
        self.priority_manager.handle_pass("player_1")
        self.priority_manager.handle_pass("player_2")

        # Verify Gray Merchant is on battlefield exactly once
        gm_perms = [p for p in self.game_state.battlefield["player_1"] if p["id"] == "gray_merchant_001"]
        self.assertEqual(len(gm_perms), 1)

        # Life totals untouched immediately upon entry before trigger resolves
        self.assertEqual(self.game_state.life_totals["player_2"], 20)
        self.assertEqual(self.game_state.life_totals["player_1"], 20)

        # Trigger auto-placed on stack via event pipeline
        self.trigger_manager.place_pending_triggers_on_stack("player_1", "player_2")
        self.assertFalse(self.game_stack.is_empty())

        # Resolve ETB trigger
        self.priority_manager.open_priority_window()
        self.priority_manager.handle_pass("player_1")
        self.priority_manager.handle_pass("player_2")

        # Devotion calculation: Gray Merchant BB=2, Swamps mana cost has 0 black mana symbols -> Devotion = 2
        self.assertEqual(self.game_state.life_totals["player_2"], 18)
        self.assertEqual(self.game_state.life_totals["player_1"], 22)

    def test_goblin_guide_attack_trigger_integration(self):
        cm = CombatManager(self.game_state, self.transport, self.seq_num_provider)
        self.game_state.battlefield["player_1"] = [{"id": "goblin_guide_001", "tapped": False, "summoning_sick": False}]

        val, msg = cm.validate_and_declare_attackers("player_1", [{"creature_id": "goblin_guide_001", "target": "player_2"}], event_bus=self.event_bus)
        self.assertTrue(val)

        # Trigger automatically detected and waiting to be placed on stack
        self.trigger_manager.place_pending_triggers_on_stack("player_1", "player_2")
        self.assertFalse(self.game_stack.is_empty())
        self.assertEqual(self.game_stack.peek().source, "goblin_guide_001")

        # Test rejected declaration produces no triggers
        self.trigger_manager.pending_triggers.clear()
        val_bad, _ = cm.validate_and_declare_attackers("player_2", [{"creature_id": "goblin_guide_001", "target": "player_1"}], event_bus=self.event_bus)
        self.assertFalse(val_bad)
        self.assertEqual(len(self.trigger_manager.pending_triggers), 0)

    def test_first_strike_damage_and_sba_integration(self):
        cm = CombatManager(self.game_state, self.transport, self.seq_num_provider)
        orchestrator = CombatOrchestrator(cm, self.game_state, self.event_bus, self.transport, self.seq_num_provider)

        cat = CardCatalog.get_instance()
        self.game_state.battlefield["player_1"] = [{"id": "fs_attacker_001", "power": 2, "toughness": 1, "tapped": True, "damage": 0}]
        self.game_state.battlefield["player_2"] = [{"id": "normal_blocker_001", "power": 2, "toughness": 1, "tapped": False, "damage": 0}]

        def_fs = CardDefinition("fs_attacker_001", {
            "name": "First Striker",
            "card_type": "Creature",
            "power": 2,
            "toughness": 1,
            "keywords": ["first_strike"]
        })
        cat.definitions["fs_attacker_001"] = def_fs

        cm.attackers = [{"creature_id": "fs_attacker_001", "target": "player_2"}]
        cm.blockers = [{"creature_id": "normal_blocker_001", "blocking_id": "fs_attacker_001"}]

        # Execute first-strike damage step
        fs_result = orchestrator.execute_combat_damage_step(is_first_strike_step=True)
        self.assertIn("normal_blocker_001", fs_result["creatures_died"])
        self.assertNotIn("normal_blocker_001", [p["id"] for p in self.game_state.battlefield["player_2"]])

        # Execute regular combat damage step
        reg_result = orchestrator.execute_combat_damage_step(is_first_strike_step=False)
        self.assertEqual(len(reg_result["damage_events"]), 0)
        self.assertIn("fs_attacker_001", [p["id"] for p in self.game_state.battlefield["player_1"]])

    def test_client_readiness_unique_decks_and_explicit_ids(self):
        client_a = ClientState(player_id="bala")
        client_b = ClientState(player_id="partner")

        deck_a = build_default_development_deck()
        deck_b = build_default_development_deck()

        valid_a, msg_a = validate_deck(deck_a)
        valid_b, msg_b = validate_deck(deck_b)

        self.assertTrue(valid_a, msg_a)
        self.assertTrue(valid_b, msg_b)
        self.assertEqual(len(deck_a), 40)
        self.assertEqual(len(set(deck_a)), 40)

        pdu_a = client_a.build_player_ready(deck_a)
        pdu_b = client_b.build_player_ready(deck_b)

        self.assertEqual(pdu_a["player_id"], "bala")
        self.assertEqual(pdu_b["player_id"], "partner")
        self.assertNotEqual(pdu_a["player_id"], pdu_b["player_id"])
        self.assertEqual(pdu_a["deck_list"], deck_a)
        self.assertEqual(pdu_b["deck_list"], deck_b)

if __name__ == "__main__":
    unittest.main()
