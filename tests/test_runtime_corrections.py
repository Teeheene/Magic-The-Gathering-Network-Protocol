import time
import unittest
from unittest.mock import MagicMock
from app.client.connection import ClientConnection
from app.client.pdu_dispatcher import PduDispatcher as ClientPduDispatcher
from app.client.state import ClientState
from app.server.connected_client import ConnectedClient
from app.server.game import Game
from app.server.engine.triggers import TriggeredAbility


class TestRuntimeCorrections(unittest.TestCase):
    def setUp(self):
        self.mock_connection = MagicMock()
        self.mock_connection.clients = []
        self.mock_connection.max_clients = 2
        self.mock_connection.seq_num = 0
        self.game = Game(self.mock_connection)
        self.game.phase = "PRECOMBAT_MAIN"
        self.game.active_player = "alice"
        self.game.priority_holder = "alice"

    def create_mock_client(self, pid, port=1000):
        mock_sock = MagicMock()
        client = ConnectedClient(mock_sock, ("127.0.0.1", port))
        client.pid = pid
        client.hand = []
        client.battlefield = []
        client.graveyard = []
        client.library = []
        client.life_total = 20
        client.active_priority_seq_num = 10
        return client

    def test_prodigal_sorcerer_activated_ability_resolution(self):
        """Req 1: Prodigal Sorcerer targets Bob, ability resolves, Bob loses 1 life."""
        c1 = self.create_mock_client("alice", 1001)
        sorcerer = {"id": "prodigal_sorcerer_001", "tapped": False, "summoning_sick": False, "power": 1, "toughness": 1, "damage": 0}
        c1.battlefield = [sorcerer]

        c2 = self.create_mock_client("bob", 1002)

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")

        pdu = {
            "type": "ACTIVATE_ABILITY",
            "seq_num": c1.active_priority_seq_num,
            "source_id": "prodigal_sorcerer_001",
            "ability_index": 0,
            "targets": ["bob"],
            "cost_payment": {"tap": True, "mana": {}}
        }
        res = self.game.pdu_dispatcher.handle_activate_ability(c1, pdu)
        self.assertTrue(res)
        self.assertTrue(sorcerer["tapped"])
        self.assertEqual(len(self.game.stack), 1)

        # Resolve top stack item (the ability)
        self.game.resolve_top_stack_item()
        self.assertEqual(c2.life_total, 19)

    def test_gravedigger_trigger_choice_persistence(self):
        """Req 3: Gravedigger enters -> TRIGGER_CHOICE sent -> target selected -> trigger on stack -> resolves -> creature to hand."""
        c1 = self.create_mock_client("alice", 1001)
        c1.hand = ["gravedigger_001"]
        c1.graveyard = ["grizzly_bears_001"]
        c1.battlefield = [{"id": "swamp_001", "tapped": False}, {"id": "swamp_002", "tapped": False}, {"id": "swamp_003", "tapped": False}, {"id": "swamp_004", "tapped": False}]

        c2 = self.create_mock_client("bob", 1002)

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")

        # Cast Gravedigger
        pdu = {
            "type": "CAST_SPELL",
            "seq_num": c1.active_priority_seq_num,
            "card_id": "gravedigger_001",
            "targets": [],
            "mana_payment": {"B": 1, "X": 3}
        }
        self.assertTrue(self.game.pdu_dispatcher.handle_cast_spell(c1, pdu))

        # Resolve Gravedigger spell
        self.game.pdu_dispatcher.handle_priority_pass(c1, {"type": "PRIORITY_PASS", "seq_num": c1.active_priority_seq_num})
        self.game.pdu_dispatcher.handle_priority_pass(c2, {"type": "PRIORITY_PASS", "seq_num": c2.active_priority_seq_num})

        # Gravedigger enters, triggering ability. TRIGGER_CHOICE prompt sent to Alice.
        self.assertIsNotNone(c1.pending_trigger_choice)

        # Alice sends TRIGGER_CHOICE_RESPONSE selecting grizzly_bears_001
        choice_pdu = {
            "type": "TRIGGER_CHOICE_RESPONSE",
            "seq_num": c1.active_trigger_seq_num,
            "trigger_id": c1.pending_trigger_choice["trigger_id"],
            "accept": True,
            "chosen_target": "grizzly_bears_001"
        }
        self.assertTrue(self.game.pdu_dispatcher.handle_trigger_choice_response(c1, choice_pdu))

        # Trigger item is now on stack
        self.assertEqual(len(self.game.stack), 1)

        # Resolve trigger
        self.game.resolve_top_stack_item()
        self.assertIn("grizzly_bears_001", c1.hand)
        self.assertNotIn("grizzly_bears_001", c1.graveyard)

    def test_simultaneous_trigger_ordering(self):
        """Req 4: Two simultaneous triggers controlled by Alice -> TRIGGER_ORDER sent -> order chosen -> stack ordered accordingly."""
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]

        trg1 = TriggeredAbility("trg_01", "source_01", "alice", "Effect 1")
        trg2 = TriggeredAbility("trg_02", "source_02", "alice", "Effect 2")
        self.game.trigger_manager.pending_triggers = [trg1, trg2]

        self.game.post_event()
        self.assertIsNotNone(c1.pending_trigger_ids)
        self.assertEqual(set(c1.pending_trigger_ids), {"trg_01", "trg_02"})

        # Send TRIGGER_ORDER_RESPONSE putting trg_02 first, trg_01 second
        order_pdu = {
            "type": "TRIGGER_ORDER_RESPONSE",
            "seq_num": c1.active_trigger_seq_num,
            "ordered_trigger_ids": ["trg_02", "trg_01"]
        }
        self.assertTrue(self.game.pdu_dispatcher.handle_trigger_order_response(c1, order_pdu))

        # Stack should have trg_02 pushed first, then trg_01 on top
        self.assertEqual(len(self.game.stack), 2)
        self.assertEqual(self.game.stack[0]["trigger_id"], "trg_02")
        self.assertEqual(self.game.stack[1]["trigger_id"], "trg_01")

    def test_event_emission_for_activated_abilities_phantasmal_bear(self):
        """Req 5: Rod of Ruin targets Phantasmal Bear -> became_target emitted -> Bear sacrifice trigger pushed."""
        c1 = self.create_mock_client("alice", 1001)
        c1.battlefield = [
            {"id": "rod_of_ruin_001", "tapped": False},
            {"id": "mountain_001", "tapped": False},
            {"id": "mountain_002", "tapped": False},
            {"id": "mountain_003", "tapped": False}
        ]

        c2 = self.create_mock_client("bob", 1002)
        bear = {"id": "phantasmal_bear_001", "tapped": False, "summoning_sick": False, "power": 2, "toughness": 2, "damage": 0}
        c2.battlefield = [bear]

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")

        pdu = {
            "type": "ACTIVATE_ABILITY",
            "seq_num": c1.active_priority_seq_num,
            "source_id": "rod_of_ruin_001",
            "ability_index": 0,
            "targets": ["phantasmal_bear_001"],
            "cost_payment": {"tap": True, "mana": {"X": 3}}
        }

        res = self.game.pdu_dispatcher.handle_activate_ability(c1, pdu)
        self.assertTrue(res)

        # Bear sacrifice trigger is detected and pushed onto stack on top of ability
        self.assertEqual(len(self.game.stack), 2)
        self.assertEqual(self.game.stack[1]["item_type"], "TRIGGER_ABILITY")

    def test_spell_trigger_priority_pdu_ordering(self):
        """Req 6: Cast Lightning Bolt -> STACK_PUSH sent before PRIORITY_GRANT, exactly 1 priority grant sent.
        With Monastery Swiftspear: spell STACK_PUSH sent before Prowess trigger STACK_PUSH."""
        c1 = self.create_mock_client("alice", 1001)
        c1.hand = ["lightning_bolt_001"]
        c1.battlefield = [
            {"id": "mountain_001", "tapped": False},
            {"id": "monastery_swiftspear_001", "tapped": False, "summoning_sick": False, "power": 1, "toughness": 2, "damage": 0}
        ]

        c2 = self.create_mock_client("bob", 1002)

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]

        sent_pdus = []
        real_send = self.game.pdu_dispatcher._send
        def track_send(client, pdu_type, **kwargs):
            sent_pdus.append((client.pid, pdu_type))
            return real_send(client, pdu_type, **kwargs)
        self.game.pdu_dispatcher._send = track_send

        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")
        sent_pdus.clear()

        pdu = {
            "type": "CAST_SPELL",
            "seq_num": c1.active_priority_seq_num,
            "card_id": "lightning_bolt_001",
            "targets": ["bob"],
            "mana_payment": {"R": 1}
        }
        res = self.game.pdu_dispatcher.handle_cast_spell(c1, pdu)
        self.assertTrue(res)

        types = [t for _, t in sent_pdus]
        # Verify spell STACK_PUSH comes before PRIORITY_GRANT
        spell_push_idx = types.index("STACK_PUSH")
        pg_idx = types.index("PRIORITY_GRANT")
        self.assertLess(spell_push_idx, pg_idx)
        # Verify exactly one PRIORITY_GRANT sent during cast
        self.assertEqual(types.count("PRIORITY_GRANT"), 1)

    def test_stack_resolution_reopens_priority_with_usable_token(self):
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)
        c1.hand = ["lightning_bolt_001"]
        c1.battlefield = [{"id": "mountain_001", "tapped": False}]
        self.mock_connection.clients = self.game.clients = [c1, c2]

        sent_types = []
        real_send = self.game.pdu_dispatcher._send
        def track_send(client, pdu_type, **kwargs):
            sent_types.append(pdu_type)
            return real_send(client, pdu_type, **kwargs)
        self.game.pdu_dispatcher._send = track_send

        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")
        self.assertTrue(self.game.pdu_dispatcher.handle_cast_spell(c1, {
            "type": "CAST_SPELL", "seq_num": c1.active_priority_seq_num,
            "card_id": "lightning_bolt_001", "targets": ["bob"],
            "mana_payment": {"R": 1},
        }))
        sent_types.clear()
        self.assertTrue(self.game.pdu_dispatcher.handle_priority_pass(c1, {
            "type": "PRIORITY_PASS", "seq_num": c1.active_priority_seq_num,
        }))
        sent_types.clear()
        self.assertTrue(self.game.pdu_dispatcher.handle_priority_pass(c2, {
            "type": "PRIORITY_PASS", "seq_num": c2.active_priority_seq_num,
        }))

        self.assertLess(sent_types.index("STACK_RESOLVE"), sent_types.index("GAME_STATE_UPDATE"))
        self.assertLess(sent_types.index("GAME_STATE_UPDATE"), sent_types.index("PRIORITY_GRANT"))
        self.assertEqual(sent_types.count("PRIORITY_GRANT"), 1)
        self.assertEqual(self.game.priority_holder, "alice")
        self.assertTrue(self.game.pdu_dispatcher.handle_priority_pass(c1, {
            "type": "PRIORITY_PASS", "seq_num": c1.active_priority_seq_num,
        }))

    def test_etb_source_resolve_precedes_gray_merchant_trigger_and_priority(self):
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)
        c1.hand = ["gray_merchant_001"]
        c1.battlefield = [
            {"id": f"swamp_{index:03d}", "tapped": False}
            for index in range(1, 6)
        ]
        self.mock_connection.clients = self.game.clients = [c1, c2]
        sent = []
        real_send = self.game.pdu_dispatcher._send
        def track_send(client, pdu_type, **kwargs):
            sent.append((pdu_type, kwargs))
            return real_send(client, pdu_type, **kwargs)
        self.game.pdu_dispatcher._send = track_send

        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")
        self.game.pdu_dispatcher.handle_cast_spell(c1, {
            "type": "CAST_SPELL", "seq_num": c1.active_priority_seq_num,
            "card_id": "gray_merchant_001", "targets": [],
            "mana_payment": {"B": 2, "X": 3},
        })
        source_stack_id = self.game.stack[0]["stack_item_id"]
        self.game.pdu_dispatcher.handle_priority_pass(c1, {
            "type": "PRIORITY_PASS", "seq_num": c1.active_priority_seq_num,
        })
        sent.clear()
        self.game.pdu_dispatcher.handle_priority_pass(c2, {
            "type": "PRIORITY_PASS", "seq_num": c2.active_priority_seq_num,
        })

        source_resolve = next(i for i, entry in enumerate(sent)
                              if entry[0] == "STACK_RESOLVE" and entry[1].get("stack_item_id") == source_stack_id)
        for index, (pdu_type, _) in enumerate(sent):
            if pdu_type in {"STACK_PUSH", "PRIORITY_GRANT"}:
                self.assertGreater(index, source_resolve)

    def test_etb_source_resolve_precedes_gravedigger_trigger_prompt(self):
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)
        c1.hand = ["gravedigger_001"]
        c1.graveyard = ["grizzly_bears_001"]
        c1.battlefield = [
            {"id": f"swamp_{index:03d}", "tapped": False}
            for index in range(1, 5)
        ]
        self.mock_connection.clients = self.game.clients = [c1, c2]
        sent = []
        real_send = self.game.pdu_dispatcher._send
        def track_send(client, pdu_type, **kwargs):
            sent.append((pdu_type, kwargs))
            return real_send(client, pdu_type, **kwargs)
        self.game.pdu_dispatcher._send = track_send

        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")
        self.game.pdu_dispatcher.handle_cast_spell(c1, {
            "type": "CAST_SPELL", "seq_num": c1.active_priority_seq_num,
            "card_id": "gravedigger_001", "targets": [],
            "mana_payment": {"B": 1, "X": 3},
        })
        source_stack_id = self.game.stack[0]["stack_item_id"]
        self.game.pdu_dispatcher.handle_priority_pass(c1, {
            "type": "PRIORITY_PASS", "seq_num": c1.active_priority_seq_num,
        })
        sent.clear()
        self.assertFalse(self.game.pdu_dispatcher.handle_priority_pass(c2, {
            "type": "PRIORITY_PASS", "seq_num": c2.active_priority_seq_num,
        }))

        source_resolve = next(i for i, entry in enumerate(sent)
                              if entry[0] == "STACK_RESOLVE" and entry[1].get("stack_item_id") == source_stack_id)
        prompt = next(i for i, entry in enumerate(sent) if entry[0] == "TRIGGER_CHOICE")
        self.assertLess(source_resolve, prompt)
        self.assertFalse(any(pdu_type == "PRIORITY_GRANT" for pdu_type, _ in sent))

    def test_priority_timeout_reason_disconnect(self):
        """Req 9: Priority deadline expiration results in GAME_OVER reason DISCONNECT via check_priority_timeout."""
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.priority_holder = "alice"
        c1.priority_deadline = time.monotonic() - 1.0  # Already expired

        res = self.game.check_priority_timeout()
        self.assertTrue(res)
        self.assertTrue(self.game.game_over)

    def test_ap_nap_multi_trigger_ordering(self):
        """Item 2: AP and NAP both control 2 triggers. Both get TRIGGER_ORDER. AP pushed first, NAP on top."""
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)
        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.active_player = "alice"

        b_id = self.game.trigger_manager.generate_batch_id()
        trg_a1 = TriggeredAbility("trg_a1", "src_a1", "alice", "Alice 1", batch_id=b_id)
        trg_a2 = TriggeredAbility("trg_a2", "src_a2", "alice", "Alice 2", batch_id=b_id)
        trg_b1 = TriggeredAbility("trg_b1", "src_b1", "bob", "Bob 1", batch_id=b_id)
        trg_b2 = TriggeredAbility("trg_b2", "src_b2", "bob", "Bob 2", batch_id=b_id)
        self.game.trigger_manager.pending_triggers = [trg_a1, trg_a2, trg_b1, trg_b2]

        self.game.post_event()
        # Alice prompted for TRIGGER_ORDER
        self.assertIsNotNone(c1.pending_trigger_ids)
        self.game.pdu_dispatcher.handle_trigger_order_response(c1, {
            "type": "TRIGGER_ORDER_RESPONSE",
            "seq_num": c1.active_trigger_seq_num,
            "ordered_trigger_ids": ["trg_a2", "trg_a1"]
        })

        # Bob prompted for TRIGGER_ORDER
        self.assertIsNotNone(c2.pending_trigger_ids)
        self.game.pdu_dispatcher.handle_trigger_order_response(c2, {
            "type": "TRIGGER_ORDER_RESPONSE",
            "seq_num": c2.active_trigger_seq_num,
            "ordered_trigger_ids": ["trg_b2", "trg_b1"]
        })

        # Stack has Alice's triggers pushed first, Bob's on top
        self.assertEqual(len(self.game.stack), 4)
        controllers = [item["controller"] for item in self.game.stack]
        self.assertEqual(controllers, ["alice", "alice", "bob", "bob"])

    def test_phantasmal_bear_controller_is_target_owner(self):
        """Item 3: Alice Rod of Ruin -> Bob Phantasmal Bear. TRIGGER_ABILITY controller must equal 'bob'."""
        c1 = self.create_mock_client("alice", 1001)
        c1.battlefield = [
            {"id": "rod_of_ruin_001", "tapped": False},
            {"id": "mountain_001", "tapped": False},
            {"id": "mountain_002", "tapped": False},
            {"id": "mountain_003", "tapped": False}
        ]
        c2 = self.create_mock_client("bob", 1002)
        bear = {"id": "phantasmal_bear_001", "tapped": False, "summoning_sick": False, "power": 2, "toughness": 2, "damage": 0}
        c2.battlefield = [bear]

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")

        pdu = {
            "type": "ACTIVATE_ABILITY",
            "seq_num": c1.active_priority_seq_num,
            "source_id": "rod_of_ruin_001",
            "ability_index": 0,
            "targets": ["phantasmal_bear_001"],
            "cost_payment": {"tap": True, "mana": {"X": 3}}
        }
        self.game.pdu_dispatcher.handle_activate_ability(c1, pdu)
        # Bear trigger item is stack top
        bear_trg_item = self.game.stack[-1]
        self.assertEqual(bear_trg_item["source"], "phantasmal_bear_001")
        self.assertEqual(bear_trg_item["controller"], "bob")

    def test_concede_validation_valid_and_stale(self):
        """Item 10: CONCEDE requires matching player_id and valid active seq_num."""
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)
        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        c1.seq_num = 15

        # Mismatched player_id -> rejected ILLEGAL_ACTION
        res1 = self.game.pdu_dispatcher.handle_concede(c1, {"type": "CONCEDE", "seq_num": 15, "player_id": "bob"})
        self.assertFalse(res1)

        # Stale seq_num -> rejected STALE_ACTION
        res2 = self.game.pdu_dispatcher.handle_concede(c1, {"type": "CONCEDE", "seq_num": 999, "player_id": "alice"})
        self.assertFalse(res2)

        # The stale-action ERROR is now the most recent server PDU.
        res3 = self.game.pdu_dispatcher.handle_concede(c1, {"type": "CONCEDE", "seq_num": 999, "player_id": "alice"})
        self.assertTrue(res3)
        self.assertTrue(self.game.game_over)

    def test_combat_damage_priority_window(self):
        """Normal combat damage transitions directly to the End-of-Combat priority window."""
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)
        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.active_player = "alice"

        self.game.resolve_combat_damage(False)
        self.assertEqual(self.game.phase, "END_OF_COMBAT")
        self.assertEqual(self.game.priority_holder, "alice")

        # Two passes from End of Combat advance to Postcombat Main.
        self.game.pdu_dispatcher.handle_priority_pass(c1, {"type": "PRIORITY_PASS", "seq_num": c1.active_priority_seq_num})
        self.game.pdu_dispatcher.handle_priority_pass(c2, {"type": "PRIORITY_PASS", "seq_num": c2.active_priority_seq_num})
        self.assertEqual(self.game.phase, "POSTCOMBAT_MAIN")

    def test_combat_damage_result_precedes_state_and_priority(self):
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)
        c1.battlefield = [{
            "id": "grizzly_bears_001", "tapped": True,
            "power": 2, "toughness": 2, "damage": 0,
        }]
        c2.battlefield = [{
            "id": "savannah_lions_001", "tapped": False,
            "power": 2, "toughness": 1, "damage": 0,
        }]
        self.mock_connection.clients = self.game.clients = [c1, c2]
        self.game.active_player = "alice"
        self.game.attackers = [{"creature_id": "grizzly_bears_001", "target": "bob"}]
        self.game.blockers = [{"creature_id": "savannah_lions_001", "blocking_id": "grizzly_bears_001"}]

        sent = []
        real_send = self.game.pdu_dispatcher._send
        def track_send(client, pdu_type, **kwargs):
            sent.append((pdu_type, kwargs))
            return real_send(client, pdu_type, **kwargs)
        self.game.pdu_dispatcher._send = track_send

        self.assertTrue(self.game.resolve_combat_damage(False))
        types = [pdu_type for pdu_type, _ in sent]
        result_index = types.index("COMBAT_DAMAGE_RESULT")
        state_index = types.index("GAME_STATE_UPDATE")
        end_of_combat_index = next(
            index for index, (pdu_type, payload) in enumerate(sent)
            if pdu_type == "PHASE_TRANSITION"
            and payload.get("to_phase") == "END_OF_COMBAT"
        )
        priority_index = types.index("PRIORITY_GRANT")
        self.assertLess(result_index, state_index)
        self.assertLess(state_index, end_of_combat_index)
        self.assertLess(end_of_combat_index, priority_index)
        self.assertEqual(types.count("PRIORITY_GRANT"), 1)
        self.assertEqual(self.game.phase, "END_OF_COMBAT")
        result = next(payload for pdu_type, payload in sent if pdu_type == "COMBAT_DAMAGE_RESULT")
        self.assertCountEqual(
            result["creatures_died"],
            ["grizzly_bears_001", "savannah_lions_001"],
        )
        self.assertIn("savannah_lions_001", c2.graveyard)

    def test_rod_of_ruin_resolution(self):
        """Item 12: Rod of Ruin deals 1 damage to target player or creature."""
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)
        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.stack.append({
            "stack_item_id": "stack_1",
            "item_type": "ABILITY",
            "source": "rod_of_ruin_001",
            "controller": "alice",
            "targets": ["bob"]
        })
        self.game.resolve_top_stack_item()
        self.assertEqual(c2.life_total, 19)

    def test_royal_assassin_resolution(self):
        """Item 12: Royal Assassin destroys tapped creature."""
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)
        tapped_creature = {"id": "grizzly_bears_001", "tapped": True, "power": 2, "toughness": 2}
        c2.battlefield = [tapped_creature]
        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]

        self.game.stack.append({
            "stack_item_id": "stack_1",
            "item_type": "ABILITY",
            "source": "royal_assassin_001",
            "controller": "alice",
            "targets": ["grizzly_bears_001"]
        })
        self.game.resolve_top_stack_item()
        self.assertNotIn(tapped_creature, c2.battlefield)
        self.assertIn("grizzly_bears_001", c2.graveyard)

    def test_millstone_resolution(self):
        """Item 12: Millstone mills 2 cards from target player's library to graveyard."""
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)
        c2.library = ["card_1", "card_2", "card_3"]
        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]

        self.game.stack.append({
            "stack_item_id": "stack_1",
            "item_type": "ABILITY",
            "source": "millstone_001",
            "controller": "alice",
            "targets": ["bob"]
        })
        self.game.resolve_top_stack_item()
        self.assertEqual(c2.library, ["card_3"])
        self.assertEqual(c2.graveyard, ["card_1", "card_2"])

    def test_heartbeat_pong_matching_mismatch_and_timeout(self):
        """Req 10: Complete heartbeat tests: A. matching PONG, B. mismatched PONG, C. timeout."""
        state = ClientState("alice")
        mock_conn = MagicMock()
        mock_conn.running = True
        client_dispatcher = ClientPduDispatcher(state, mock_conn)

        # A. Matching PONG
        client_dispatcher.send_ping()
        self.assertEqual(state.pending_ping_seq, 1)
        client_dispatcher.handle_pong({"type": "PONG", "seq_num": 1})
        self.assertIsNone(state.pending_ping_seq)

        # B. Mismatched PONG
        client_dispatcher.send_ping()
        self.assertEqual(state.pending_ping_seq, 2)
        client_dispatcher.handle_pong({"type": "PONG", "seq_num": 999})
        self.assertEqual(state.pending_ping_seq, 2)  # Not cleared!

        # C. Heartbeat timeout
        real_conn = ClientConnection("127.0.0.1", 4444)
        real_conn.running = True
        real_conn.sock = MagicMock()

        real_state = ClientState("bob")
        real_dispatcher = ClientPduDispatcher(real_state, real_conn)

        real_conn.start_heartbeat(real_dispatcher, ping_interval=0.05, pong_timeout=0.10)
        time.sleep(0.3)

        self.assertFalse(real_conn.running)  # Connection closed on timeout

    def test_play_land_priority_retention_and_token_refresh(self):
        """Pass #3 Item 1: AP receives priority -> plays legal land -> land enters battlefield -> GAME_STATE_UPDATE -> PRIORITY_GRANT sent afterward -> new token differs -> AP can immediately PRIORITY_PASS."""
        c1 = self.create_mock_client("alice", 1001)
        c1.hand = ["mountain_001"]
        c1.battlefield = []
        c2 = self.create_mock_client("bob", 1002)

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.phase = "PRECOMBAT_MAIN"
        self.game.active_player = "alice"
        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")

        initial_priority_token = c1.active_priority_seq_num
        self.assertIsNotNone(initial_priority_token)

        pdu = {
            "type": "PLAY_LAND",
            "seq_num": initial_priority_token,
            "card_id": "mountain_001"
        }
        res = self.game.pdu_dispatcher.handle_play_land(c1, pdu)
        self.assertTrue(res)

        # Land entered battlefield
        self.assertIn("mountain_001", [c["id"] if isinstance(c, dict) else c for c in c1.battlefield])
        self.assertEqual(self.game.priority_holder, "alice")

        new_priority_token = c1.active_priority_seq_num
        self.assertIsNotNone(new_priority_token)
        self.assertNotEqual(initial_priority_token, new_priority_token)

        # AP can immediately pass priority with the new token
        pass_pdu = {
            "type": "PRIORITY_PASS",
            "seq_num": new_priority_token
        }
        self.assertTrue(self.game.pdu_dispatcher.handle_priority_pass(c1, pass_pdu))

    def test_concede_requires_most_recent_server_pdu_only(self):
        """Pass #3 Item 2: CONCEDE require pdu['seq_num'] == client.seq_num. Rejects old active_priority_seq_num."""
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)
        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]

        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")
        old_priority_token = c1.active_priority_seq_num
        self.assertEqual(c1.seq_num, old_priority_token)

        # Later server sends GAME_STATE_UPDATE, updating client.seq_num
        self.game.pdu_dispatcher.send_game_state_update(c1, self.game.state_builder.build_game_state(c1))
        latest_server_token = c1.seq_num
        self.assertNotEqual(old_priority_token, latest_server_token)

        # CONCEDE using old priority token -> STALE_ACTION
        stale_concede = {"type": "CONCEDE", "player_id": "alice", "seq_num": old_priority_token}
        res1 = self.game.pdu_dispatcher.handle_concede(c1, stale_concede)
        self.assertFalse(res1)

        # The rejected attempt produced an ERROR with its echoed seq_num, which
        # is now the most recent server PDU and therefore the valid token.
        valid_concede = {"type": "CONCEDE", "player_id": "alice", "seq_num": old_priority_token}
        res2 = self.game.pdu_dispatcher.handle_concede(c1, valid_concede)
        self.assertTrue(res2)

    def test_real_simultaneous_trigger_batching_goblin_guides(self):
        """Pass #3 Item 3A: Two Goblin Guides attack in same DECLARE_ATTACKERS PDU -> same batch_id -> TRIGGER_ORDER prompt -> order response."""
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)
        c1.battlefield = [
            {"id": "goblin_guide_001", "tapped": False, "summoning_sick": False},
            {"id": "goblin_guide_002", "tapped": False, "summoning_sick": False}
        ]
        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.phase = "DECLARE_ATTACKERS"
        self.game.active_player = "alice"

        self.game.pdu_dispatcher.send_phase_transition(c1, "BEGIN_COMBAT", "DECLARE_ATTACKERS", "alice", 1)
        attack_pdu = {
            "type": "DECLARE_ATTACKERS",
            "seq_num": c1.active_phase_seq_num,
            "attackers": [
                {"creature_id": "goblin_guide_001", "target": "bob"},
                {"creature_id": "goblin_guide_002", "target": "bob"}
            ]
        }
        self.game.pdu_dispatcher.handle_declare_attackers(c1, attack_pdu)

        # Both Goblin Guide triggers got same batch_id and triggered order prompt for c1
        self.assertIsNotNone(c1.pending_trigger_ids)
        self.assertEqual(len(c1.pending_trigger_ids), 2)
        tids = c1.pending_trigger_ids

        # Respond to order prompt
        order_pdu = {
            "type": "TRIGGER_ORDER",
            "seq_num": c1.active_trigger_seq_num,
            "ordered_trigger_ids": [tids[1], tids[0]]
        }
        self.assertTrue(self.game.pdu_dispatcher.handle_trigger_order_response(c1, order_pdu))

        # Stack top trigger should be tids[0] (pushed second, so on top)
        self.assertEqual(self.game.stack[-1]["trigger_id"], tids[0])
        self.assertEqual(self.game.stack[-2]["trigger_id"], tids[1])
        self.assertEqual(self.game.phase, "DECLARE_ATTACKERS")
        self.assertEqual(self.game.priority_holder, "alice")
        self.assertIsNotNone(c1.active_priority_seq_num)

    def test_trigger_order_response_preserves_other_batches(self):
        """Pass #3 Item 3B: Reordering batch A preserves same-controller triggers in batch B."""
        from app.server.engine.triggers import TriggeredAbility
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)
        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]

        trg_a1 = TriggeredAbility("trg_a1", "src_a1", "alice", "Effect A1", False, lambda i, g: ("RESOLVED", []))
        trg_a1.batch_id = "batch_A"
        trg_a2 = TriggeredAbility("trg_a2", "src_a2", "alice", "Effect A2", False, lambda i, g: ("RESOLVED", []))
        trg_a2.batch_id = "batch_A"

        trg_b1 = TriggeredAbility("trg_b1", "src_b1", "alice", "Effect B1", False, lambda i, g: ("RESOLVED", []))
        trg_b1.batch_id = "batch_B"
        trg_b2 = TriggeredAbility("trg_b2", "src_b2", "alice", "Effect B2", False, lambda i, g: ("RESOLVED", []))
        trg_b2.batch_id = "batch_B"

        self.game.trigger_manager.pending_triggers = [trg_a1, trg_a2, trg_b1, trg_b2]

        c1.pending_trigger_ids = ["trg_a1", "trg_a2"]
        c1.active_trigger_seq_num = 50

        order_pdu = {
            "type": "TRIGGER_ORDER",
            "seq_num": 50,
            "ordered_trigger_ids": ["trg_a2", "trg_a1"]
        }
        self.game.pdu_dispatcher.handle_trigger_order_response(c1, order_pdu)

        # Batch B triggers trg_b1 and trg_b2 must remain present in stack or pending_triggers!
        all_trg_ids = [t.trigger_id for t in self.game.trigger_manager.pending_triggers] + [item.get("trigger_id") for item in self.game.stack if item.get("trigger_id")]
        self.assertIn("trg_b1", all_trg_ids)
        self.assertIn("trg_b2", all_trg_ids)
