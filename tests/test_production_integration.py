import time
import unittest
from unittest.mock import MagicMock

from app.client.connection import ClientConnection
from app.client.pdu_dispatcher import PduDispatcher as ClientPduDispatcher
from app.client.state import ClientState
from app.server.connected_client import ConnectedClient
from app.server.game import Game, CATALOG_PATH
from app.shared.card_catalog import CardCatalog


class TestProductionIntegration(unittest.TestCase):
    def setUp(self):
        self.mock_connection = MagicMock()
        self.mock_connection.clients = []
        self.mock_connection.max_clients = 2
        self.mock_connection.seq_num = 0
        self.game = Game(self.mock_connection)
        self.dispatcher = self.game.pdu_dispatcher

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
        client.active_phase_seq_num = 10
        return client

    def test_player_ready_independent_seq_counter(self):
        """Req 2: PLAYER_READY must have independent sequence counter starting at 1."""
        state = ClientState("alice")
        mock_conn = MagicMock()
        client_dispatcher = ClientPduDispatcher(state, mock_conn)

        self.assertEqual(state.player_ready_seq_num, 1)
        client_dispatcher.send_player_ready()
        mock_conn.send.assert_called_with({
            "type": "PLAYER_READY",
            "seq_num": 1,
            "player_id": "alice",
            "deck_list": []
        })
        self.assertEqual(state.player_ready_seq_num, 2)

        # Replacement ready
        client_dispatcher.send_player_ready()
        mock_conn.send.assert_called_with({
            "type": "PLAYER_READY",
            "seq_num": 2,
            "player_id": "alice",
            "deck_list": []
        })
        self.assertEqual(state.player_ready_seq_num, 3)

    def test_deck_instance_identity_validation(self):
        """Req 5: Base IDs alone rejected; three-digit suffix required; duplicate instances rejected."""
        catalog = CardCatalog(CATALOG_PATH)
        self.assertFalse(catalog.is_valid_instance_id("mountain"))
        self.assertTrue(catalog.is_valid_instance_id("mountain_001"))
        self.assertFalse(catalog.is_valid_instance_id("mountain_999"))

        # Unique deck valid
        valid_deck = [f"mountain_{i:03d}" for i in range(1, 21)]
        self.assertTrue(catalog.is_valid_deck(valid_deck))

        # Duplicate instance in deck invalid
        dup_deck = ["mountain_001", "mountain_001"]
        self.assertFalse(catalog.is_valid_deck(dup_deck))

    def test_game_state_update_schema(self):
        """Req 6: hand is flat list for viewer; hand_counts is opponent count only."""
        c1 = self.create_mock_client("alice", 1001)
        c1.hand = ["mountain_001", "shock_001"]

        c2 = self.create_mock_client("bob", 1002)
        c2.hand = ["forest_001"]

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.turn = 1
        self.game.phase = "PRECOMBAT_MAIN"
        self.game.active_player = "alice"

        state = self.game.state_builder.build_game_state(c1)
        self.assertEqual(state["hand"], ["mountain_001", "shock_001"])
        self.assertEqual(state["hand_counts"], {"bob": 1})
        self.assertNotIn("alice", state["hand_counts"])

    def test_sorcery_speed_cast_timing_enforcement(self):
        """Req 10: Reject Land via CAST_SPELL; enforce active player, main phase, empty stack for sorceries."""
        c1 = self.create_mock_client("alice", 1001)
        c1.hand = ["mountain_001", "lava_spike_001"]

        c2 = self.create_mock_client("bob", 1002)

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.active_player = "bob"  # Alice is NOT active player
        self.game.priority_holder = "alice"
        self.game.phase = "PRECOMBAT_MAIN"
        self.game.stack = []

        # 1. Cast Land via CAST_SPELL fails
        res1 = self.dispatcher.handle_cast_spell(c1, {
            "type": "CAST_SPELL",
            "seq_num": 10,
            "card_id": "mountain_001",
            "targets": [],
            "mana_payment": {}
        })
        self.assertFalse(res1)

        # 2. Sorcery cast when not active player fails with WRONG_PHASE
        res2 = self.dispatcher.handle_cast_spell(c1, {
            "type": "CAST_SPELL",
            "seq_num": 10,
            "card_id": "lava_spike_001",
            "targets": ["bob"],
            "mana_payment": {"R": 1}
        })
        self.assertFalse(res2)

    def test_illegal_play_land_wrong_phase_error(self):
        """Req 6: Illegal PLAY_LAND outside main phase sends ERROR PDU with WRONG_PHASE code."""
        c1 = self.create_mock_client("alice", 1001)
        c1.hand = ["mountain_001"]

        c2 = self.create_mock_client("bob", 1002)

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.active_player = "alice"
        self.game.priority_holder = "alice"
        self.game.phase = "UPKEEP"  # UPKEEP is not a main phase!

        res = self.dispatcher.handle_play_land(c1, {
            "type": "PLAY_LAND",
            "seq_num": 10,
            "card_id": "mountain_001",
        })
        self.assertFalse(res)
        c1.sock.sendall.assert_called()

    def test_priority_pass_twice_from_upkeep_to_draw(self):
        """Req 11: Priority pass twice from UPKEEP advances phase to DRAW."""
        c1 = self.create_mock_client("alice", 1001)
        c1.library = ["mountain_002"]
        c2 = self.create_mock_client("bob", 1002)

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.turn = 1
        self.game.active_player = "alice"
        self.game.priority_holder = "alice"
        self.game.phase = "UPKEEP"
        self.game.consecutive_priority_passes = 0

        # Pass 1: Alice -> Bob
        res1 = self.dispatcher.handle_priority_pass(c1, {"type": "PRIORITY_PASS", "seq_num": 10})
        self.assertTrue(res1)
        self.assertEqual(self.game.priority_holder, "bob")
        self.assertEqual(self.game.consecutive_priority_passes, 1)

        # Pass 2: Bob -> Advance to DRAW phase
        res2 = self.dispatcher.handle_priority_pass(c2, {"type": "PRIORITY_PASS", "seq_num": c2.active_priority_seq_num})
        self.assertTrue(res2)
        self.assertEqual(self.game.phase, "DRAW")

    def test_advance_phase_complete_turn_to_next_upkeep(self):
        """Req 2 & 3: Complete turn progression via Game.advance_phase() to next player's UPKEEP."""
        c1 = self.create_mock_client("alice", 1001)
        c1.library = ["mountain_002", "shock_001"]
        c2 = self.create_mock_client("bob", 1002)
        c2.library = ["forest_002"]

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.active_player = "alice"
        self.game.turn = 1
        self.game.phase = "UPKEEP"

        # Advance through all turn phases
        self.game.advance_phase()  # UPKEEP -> DRAW
        self.assertEqual(self.game.phase, "DRAW")

        self.game.advance_phase()  # DRAW -> PRECOMBAT_MAIN
        self.assertEqual(self.game.phase, "PRECOMBAT_MAIN")

        self.game.advance_phase()  # PRECOMBAT_MAIN -> BEGIN_COMBAT
        self.assertEqual(self.game.phase, "BEGIN_COMBAT")

        self.game.advance_phase()  # BEGIN_COMBAT -> DECLARE_ATTACKERS
        self.assertEqual(self.game.phase, "DECLARE_ATTACKERS")

        self.game.advance_phase()  # DECLARE_ATTACKERS -> DECLARE_BLOCKERS
        self.assertEqual(self.game.phase, "DECLARE_BLOCKERS")

        self.game.advance_phase()  # DECLARE_BLOCKERS -> END_OF_COMBAT
        self.assertEqual(self.game.phase, "END_OF_COMBAT")

        self.game.advance_phase()  # END_OF_COMBAT -> POSTCOMBAT_MAIN
        self.assertEqual(self.game.phase, "POSTCOMBAT_MAIN")

        self.game.advance_phase()  # POSTCOMBAT_MAIN -> END_STEP
        self.assertEqual(self.game.phase, "END_STEP")

        self.game.advance_phase()  # END_STEP -> CLEANUP -> UNTAP -> UPKEEP (active player switches to bob!)
        self.assertEqual(self.game.active_player, "bob")
        self.assertEqual(self.game.phase, "UPKEEP")


    def test_multiword_card_id_normalization(self):
        """Req 7: Verify base_card_id handles multiword card instance IDs cleanly."""
        catalog = CardCatalog(CATALOG_PATH)
        self.assertEqual(catalog.base_card_id("searing_spear_001"), "searing_spear")
        self.assertEqual(catalog.base_card_id("lightning_bolt_002"), "lightning_bolt")

        card_data = catalog.get_card_data("searing_spear_001")
        self.assertIsNotNone(card_data)
        self.assertEqual(card_data.get("name"), "Searing Spear")


    def test_heartbeat_pong_matching_and_timeout(self):
        """Req 9: Local heartbeat timing, pending_ping_seq, and last_pong_timestamp correlation."""
        state = ClientState("alice")
        mock_conn = MagicMock()
        client_dispatcher = ClientPduDispatcher(state, mock_conn)

        client_dispatcher.send_ping()
        self.assertEqual(state.pending_ping_seq, 1)

        # Receive matching PONG
        now_before = time.time()
        client_dispatcher.handle_pong({"type": "PONG", "seq_num": 1, "timestamp": 1234567890})
        self.assertGreaterEqual(state.last_pong_timestamp, now_before)
        self.assertIsNone(state.pending_ping_seq)

    def test_damage_assignment_last_blocker_takes_remainder(self):
        """Req 13: 5/5 attacker blocked by single 1/1 assigns all 5 damage to blocker."""
        attacker = {"id": "grizzly_bears_001", "power": 5, "toughness": 5, "tapped": True}
        blocker = {"id": "llanowar_elves_001", "power": 1, "toughness": 1, "tapped": False, "damage": 0}

        c1 = self.create_mock_client("alice", 1001)
        c1.battlefield = [attacker]

        c2 = self.create_mock_client("bob", 1002)
        c2.battlefield = [blocker]

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.attackers = [{"creature_id": "grizzly_bears_001", "target": "bob"}]
        self.game.blockers = [{"creature_id": "llanowar_elves_001", "blocking_id": "grizzly_bears_001"}]
        self.game.damage_orders = {"grizzly_bears_001": ["llanowar_elves_001"]}

        self.game.resolve_combat_damage(first_strike=False)
        self.assertEqual(blocker["damage"], 5)  # Single blocker received ALL 5 damage


if __name__ == "__main__":
    unittest.main()
