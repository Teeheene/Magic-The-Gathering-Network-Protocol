import unittest
import socket
import threading
import json
import struct
from app.shared.cards import CardCatalog
from app.client.state import ClientState
from app.client.actions import ClientActionFactory
from app.client.transport import ClientTransport, recv_exact
from app.server.game.game_state import GameState
from app.server.game.stack import GameStack, StackItem
from app.server.game.combat import CombatManager
from app.server.game.triggers import TriggerManager, calculate_devotion_to_black
from app.server.game.sba import StateBasedActions
from app.server.game.events import GameEvent
from app.server.game.effect_handlers import resolve_counterspell, resolve_gray_merchant

class TestCoreContracts(unittest.TestCase):
    def test_pdu_action_factory_schemas(self):
        ready = ClientActionFactory.player_ready(1, "player_1", ["mountain_001"])
        self.assertEqual(ready, {"type": "PLAYER_READY", "seq_num": 1, "player_id": "player_1", "deck_list": ["mountain_001"]})

        cast = ClientActionFactory.cast_spell(20, "lightning_bolt_001", ["player_2"], {"R": 1})
        self.assertEqual(cast["type"], "CAST_SPELL")
        self.assertEqual(cast["mana_payment"], {"R": 1})

        act = ClientActionFactory.activate_ability(21, "sorcerer_001", 0, ["player_2"], {"tap": True})
        self.assertEqual(act["type"], "ACTIVATE_ABILITY")
        self.assertEqual(act["source_id"], "sorcerer_001")
        self.assertEqual(act["cost_payment"], {"tap": True})

        atk = ClientActionFactory.declare_attackers(30, [{"creature_id": "goblin_001", "target": "player_2"}])
        self.assertEqual(atk["type"], "DECLARE_ATTACKERS")
        self.assertIn("attackers", atk)

        blk = ClientActionFactory.declare_blockers(31, [{"creature_id": "bears_001", "blocking_id": "goblin_001"}])
        self.assertEqual(blk["type"], "DECLARE_BLOCKERS")
        self.assertIn("blockers", blk)

        conc = ClientActionFactory.concede(50, "player_1")
        self.assertEqual(conc, {"type": "CONCEDE", "seq_num": 50, "player_id": "player_1"})

    def test_personalized_hand_object_shape(self):
        gs = GameState(["player_1", "player_2"])
        gs.hands["player_1"] = ["mountain_001", "shock_001"]
        gs.hands["player_2"] = ["forest_001", "bear_001"]

        pstate = gs.get_personalized_state("player_1")
        self.assertEqual(pstate["hand"], {"player_1": ["mountain_001", "shock_001"]})
        self.assertEqual(pstate["hand_counts"], {"player_2": 2})

    def test_client_sequence_tracking(self):
        cs = ClientState()
        cs.update_authoritative_state({"type": "PRIORITY_GRANT", "seq_num": 105})
        cs.update_authoritative_state({"type": "PHASE_TRANSITION", "seq_num": 200})

        pass_action = cs.build_priority_pass()
        self.assertEqual(pass_action["seq_num"], 105)

        atk_action = cs.build_declare_attackers([])
        self.assertEqual(atk_action["seq_num"], 200)

    def test_counterspell_removes_internal_stack_item(self):
        gs = GameState(["player_1", "player_2"])
        stack = GameStack(gs)

        # Player 1 casts Lightning Bolt
        bolt_item = StackItem(
            stack_item_id="stk_01",
            item_type="SPELL",
            source="lightning_bolt_001",
            controller="player_1",
            targets=["player_2"]
        )
        stack.push(bolt_item)

        # Player 2 casts Counterspell targeting Lightning Bolt
        cs_item = StackItem(
            stack_item_id="stk_02",
            item_type="SPELL",
            source="counterspell_001",
            controller="player_2",
            targets=["stk_01"],
            effect_fn=lambda item, state, st_ref=stack: resolve_counterspell(item, state, st_ref)
        )
        stack.push(cs_item)

        # Resolve Counterspell
        res_cs = stack.resolve_top()
        self.assertEqual(res_cs["result"], "RESOLVED")
        
        # Verify Lightning Bolt was removed from internal stack AND serialized stack
        self.assertTrue(stack.is_empty())
        self.assertEqual(len(gs.stack), 0)

        # Verify next resolve is empty and Bolt does not resolve
        res_next = stack.resolve_top()
        self.assertEqual(res_next["result"], "EMPTY")
        self.assertEqual(gs.life_totals["player_2"], 20)

    def test_combat_first_strike_skipping(self):
        gs = GameState(["player_1", "player_2"])
        cat = CardCatalog.get_instance()

        cm = CombatManager(gs)
        # Setup normal attacker (Goblin Guide has no first strike)
        gs.battlefield["player_1"].append({"id": "goblin_guide_001", "tapped": True, "power": 2, "toughness": 2, "damage": 0})
        cm.attackers = [{"creature_id": "goblin_guide_001", "target": "player_2"}]

        # First strike step -> Normal creature should NOT deal damage
        pdu_fs = cm.resolve_combat_damage(is_first_strike_step=True)
        self.assertEqual(len(pdu_fs["damage_events"]), 0)
        self.assertEqual(gs.life_totals["player_2"], 20)

        # Regular combat step -> Normal creature deals damage
        pdu_reg = cm.resolve_combat_damage(is_first_strike_step=False)
        self.assertEqual(len(pdu_reg["damage_events"]), 1)
        self.assertEqual(gs.life_totals["player_2"], 18)

    def test_gray_merchant_mandatory_etb_trigger(self):
        gs = GameState(["player_1", "player_2"])
        stack = GameStack(gs)
        tm = TriggerManager(gs, stack)

        # Spell resolution: places Gray Merchant on battlefield
        res_changes = resolve_gray_merchant(
            StackItem("stk_01", "SPELL", "gray_merchant_001", "player_1", []),
            gs
        )
        self.assertEqual(res_changes[0]["change_type"], "ENTER_BATTLEFIELD")
        self.assertEqual(gs.life_totals["player_2"], 20) # No damage yet before trigger resolves

        # Detect ETB event
        evt = GameEvent("permanent_entered", {"card_id": "gray_merchant_001", "controller": "player_1"})
        detected = tm.detect_triggers_for_event(evt)
        self.assertEqual(len(detected), 1)
        self.assertFalse(detected[0].optional)

        # Place trigger on stack and resolve
        tm.place_pending_triggers_on_stack("player_1", "player_2")
        self.assertFalse(stack.is_empty())

        stack.resolve_top()
        self.assertEqual(gs.life_totals["player_2"], 18) # Drained 2 life (Gray Merchant cost BB)
        self.assertEqual(gs.life_totals["player_1"], 22)

    def test_transport_payload_limits(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.bind(("127.0.0.1", 0))
        host, port = server_sock.getsockname()
        server_sock.listen(1)

        t = ClientTransport()
        t.connect(host, port)

        with self.assertRaises(ValueError):
            t.send_pdu({"large": "x" * 70000})

        t.close()
        server_sock.close()

if __name__ == "__main__":
    unittest.main()
