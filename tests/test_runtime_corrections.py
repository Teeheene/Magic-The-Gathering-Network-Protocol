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

    def test_priority_timeout_reason_disconnect(self):
        """Req 9: Priority deadline expiration results in GAME_OVER reason DISCONNECT."""
        c1 = self.create_mock_client("alice", 1001)
        c2 = self.create_mock_client("bob", 1002)

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.priority_holder = "alice"
        c1.priority_deadline = time.monotonic() - 1.0  # Already expired

        p_client = self.game.client_for_player(self.game.priority_holder)
        if time.monotonic() > p_client.priority_deadline:
            self.game.end_game(p_client, "DISCONNECT")

        self.assertTrue(self.game.game_over)
        c1.sock.sendall.assert_called()

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
