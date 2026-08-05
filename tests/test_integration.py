import unittest
from typing import Dict, List, Any
from app.server.game.game_state import GameState
from app.server.game.stack import GameStack
from app.server.game.priority import PriorityManager
from app.server.game.gameplay_handler import GameplayHandler
from app.server.game.combat import CombatManager
from app.server.game.triggers import TriggerManager
from app.server.game.sba import StateBasedActions
from app.server.game.events import GameEvent
from app.client.__main__ import ClientState
from tests.test_priority_stack import MockTransport, MockPhaseManager, MockSeqNumProvider

class TestGameplayIntegrationScenario(unittest.TestCase):
    def setUp(self):
        self.players = ["player_1", "player_2"]
        self.state = GameState(self.players)
        self.state.active_player = "player_1"
        self.state.phase = "PRECOMBAT_MAIN"
        self.state.turn = 1

        self.transport = MockTransport()
        self.seq_provider = MockSeqNumProvider()
        self.phase_mgr = MockPhaseManager(active_player="player_1", current_phase="PRECOMBAT_MAIN")
        self.stack = GameStack(self.state, self.transport, self.seq_provider)
        self.priority_mgr = PriorityManager(self.state, self.stack, self.phase_mgr, self.transport, self.seq_provider)
        self.gameplay = GameplayHandler(self.state, self.stack, self.priority_mgr, self.phase_mgr)
        self.combat = CombatManager(self.state, self.transport, self.seq_provider)
        self.trigger_mgr = TriggerManager(self.state, self.stack, self.transport, self.seq_provider)

        self.client_p1 = ClientState()
        self.client_p2 = ClientState()

    def update_clients(self):
        st1 = self.state.get_personalized_state("player_1")
        st2 = self.state.get_personalized_state("player_2")
        seq = self.seq_provider.next_seq_num()
        self.client_p1.update_authoritative_state({"type": "GAME_STATE_UPDATE", "seq_num": seq, "state": st1})
        self.client_p2.update_authoritative_state({"type": "GAME_STATE_UPDATE", "seq_num": seq, "state": st2})

    def test_full_gameplay_integration_flow(self):
        # Setup hands & libraries
        self.state.hands["player_1"] = ["mountain_001", "goblin_guide_001", "giant_growth_001"]
        self.state.hands["player_2"] = ["grizzly_bears_001"]
        self.state.libraries["player_2"] = ["mountain_002"] # Defending player's top library card
        self.update_clients()

        # Step 1: Player 1 plays a land
        self.priority_mgr.open_priority_window()
        res_land = self.gameplay.play_land("player_1", "mountain_001")
        self.assertEqual(res_land["status"], "SUCCESS")
        self.assertNotIn("mountain_001", self.state.hands["player_1"])
        self.assertEqual(len(self.state.battlefield["player_1"]), 1)

        # Step 2: Player 1 casts a creature (Goblin Guide)
        res_cast = self.gameplay.cast_spell("player_1", "goblin_guide_001", [], {"R": 1})
        self.assertEqual(res_cast["status"], "SUCCESS")
        self.assertEqual(len(self.state.stack), 1)

        # Step 3: Both pass -> Creature resolves and enters battlefield
        self.priority_mgr.handle_pass("player_1")
        self.priority_mgr.handle_pass("player_2")
        self.assertEqual(len(self.state.stack), 0)
        self.assertEqual(len(self.state.battlefield["player_1"]), 2) # Mountain + Goblin Guide

        # Step 4: Later spell modifies creature (Giant Growth)
        self.state.battlefield["player_1"].append({"id": "forest_001", "tapped": False})
        res_gg = self.gameplay.cast_spell("player_1", "giant_growth_001", ["goblin_guide_001"], {"G": 1})
        self.assertEqual(res_gg["status"], "SUCCESS", msg=res_gg.get("message", ""))
        self.priority_mgr.handle_pass("player_1")
        self.priority_mgr.handle_pass("player_2")

        gg_creature = next(p for p in self.state.battlefield["player_1"] if p["id"] == "goblin_guide_001")
        self.assertEqual(gg_creature["power"], 5) # 2 + 3 = 5

        # Step 5: Creature attacks & triggers attack ability
        self.phase_mgr.current_phase = "DECLARE_ATTACKERS"
        # Clear summoning sickness for test attack
        gg_creature["summoning_sick"] = False
        val_atk, msg_atk = self.combat.validate_and_declare_attackers("player_1", [{"creature_id": "goblin_guide_001", "target": "player_2"}])
        self.assertTrue(val_atk)

        # Trigger detection for attack
        evt = GameEvent("attacker_declared", {"creature_id": "goblin_guide_001"})
        self.trigger_mgr.detect_triggers_for_event(evt)
        self.trigger_mgr.place_pending_triggers_on_stack("player_1", "player_2")
        self.assertEqual(len(self.state.stack), 1) # Trigger on stack

        # Resolve trigger
        self.priority_mgr.open_priority_window()
        self.priority_mgr.handle_pass("player_1")
        self.priority_mgr.handle_pass("player_2")
        # Defending player's top land card was revealed and put into hand
        self.assertIn("mountain_002", self.state.hands["player_2"])

        # Step 6: Opponent takes damage
        self.phase_mgr.current_phase = "COMBAT_DAMAGE"
        dmg_pdu = self.combat.resolve_combat_damage(is_first_strike_step=False)
        self.assertEqual(self.state.life_totals["player_2"], 15) # 20 - 5 = 15

        # Step 7: State-based actions are applied
        changes, events, game_over = StateBasedActions.check_and_apply(self.state)
        self.assertIsNone(game_over) # Player 2 still alive at 15 life

        # Step 8: Both clients receive correct personalized state
        self.update_clients()
        
        # Player 1 sees own hand, opponent hand counts
        r1 = self.client_p1.render()
        r2 = self.client_p2.render()

        self.assertIn("Life Totals: {'player_1': 20, 'player_2': 15}", r1)
        self.assertIn("Life Totals: {'player_1': 20, 'player_2': 15}", r2)

if __name__ == "__main__":
    unittest.main()
