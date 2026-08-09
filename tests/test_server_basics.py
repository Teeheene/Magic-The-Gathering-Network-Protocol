import unittest
from unittest.mock import MagicMock

from app.server.connected_client import ConnectedClient
from app.server.game import Game
from app.server.game_state import StateBuilder


class TestServerBasics(unittest.TestCase):
    def setUp(self):
        self.mock_connection = MagicMock()
        self.mock_connection.clients = []
        self.mock_connection.max_clients = 2
        self.mock_connection.seq_num = 0
        self.game = Game(self.mock_connection)

    def test_lobby_state_builder(self):
        builder = StateBuilder(self.mock_connection)
        state = builder.build_lobby_state()
        self.assertEqual(state["phase"], "LOBBY")
        self.assertEqual(state["players_ready"], 0)
        self.assertEqual(len(state["waiting_for"]), 2)

    def test_player_ready_handshake(self):
        dispatcher = self.game.pdu_dispatcher
        mock_socket = MagicMock()
        client = ConnectedClient(mock_socket, ("127.0.0.1", 12345))

        ready_pdu = {
            "type": "PLAYER_READY",
            "seq_num": 1,
            "player_id": "alice",
            "deck_list": [f"mountain_{i:03d}" for i in range(1, 21)],
        }

        accepted = dispatcher.handle_player_ready(client, ready_pdu)
        self.assertTrue(accepted)
        self.assertEqual(client.pid, "alice")
        self.assertEqual(len(client.deck_list), 20)
        self.assertIn(client, self.mock_connection.clients)

    def test_duplicate_player_id_rejection(self):
        dispatcher = self.game.pdu_dispatcher
        mock_socket1 = MagicMock()
        client1 = ConnectedClient(mock_socket1, ("127.0.0.1", 12345))
        dispatcher.handle_player_ready(client1, {
            "type": "PLAYER_READY",
            "seq_num": 1,
            "player_id": "alice",
            "deck_list": [f"mountain_{i:03d}" for i in range(1, 21)],
        })

        mock_socket2 = MagicMock()
        client2 = ConnectedClient(mock_socket2, ("127.0.0.1", 12346))
        accepted = dispatcher.handle_player_ready(client2, {
            "type": "PLAYER_READY",
            "seq_num": 2,
            "player_id": "alice",
            "deck_list": [f"mountain_{i:03d}" for i in range(1, 21)],
        })
        self.assertFalse(accepted)
        mock_socket2.sendall.assert_called()

    def test_invalid_deck_rejection(self):
        dispatcher = self.game.pdu_dispatcher
        mock_socket = MagicMock()
        client = ConnectedClient(mock_socket, ("127.0.0.1", 12345))

        accepted = dispatcher.handle_player_ready(client, {
            "type": "PLAYER_READY",
            "seq_num": 1,
            "player_id": "alice",
            "deck_list": ["invalid_card_999"] * 20,
        })
        self.assertFalse(accepted)
        mock_socket.sendall.assert_called()

    def test_lobby_player_ready_replacement(self):
        dispatcher = self.game.pdu_dispatcher
        mock_socket = MagicMock()
        client = ConnectedClient(mock_socket, ("127.0.0.1", 12345))

        dispatcher.handle_player_ready(client, {
            "type": "PLAYER_READY",
            "seq_num": 1,
            "player_id": "alice",
            "deck_list": [f"mountain_{i:03d}" for i in range(1, 21)],
        })
        self.assertEqual(len(self.mock_connection.clients), 1)

        # Replace deck in lobby
        accepted = dispatcher.handle_player_ready(client, {
            "type": "PLAYER_READY",
            "seq_num": 2,
            "player_id": "alice",
            "deck_list": [f"forest_{i:03d}" for i in range(1, 21)],
        })
        self.assertTrue(accepted)
        self.assertEqual(len(self.mock_connection.clients), 1)
        self.assertEqual(client.deck_list[0], "forest_001")


    def test_verbose_logging(self):
        import io
        import sys

        mock_socket = MagicMock()
        client = ConnectedClient(mock_socket, ("127.0.0.1", 12345), verbose=True)

        captured = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = captured
        try:
            client.send({"type": "PONG", "seq_num": 1, "timestamp": 12345})
        finally:
            sys.stdout = old_stdout

        output = captured.getvalue()
        self.assertIn("[SERVER SENT PDU]", output)
        self.assertIn('"type": "PONG"', output)

    def test_defender_and_vigilance_combat(self):
        dispatcher = self.game.pdu_dispatcher
        mock_socket1 = MagicMock()
        client = ConnectedClient(mock_socket1, ("127.0.0.1", 12345))
        client.pid = "alice"
        client.active_phase_seq_num = 10
        client.life_total = 20

        client.graveyard = []
        client.hand = []
        client.library = []
        client.battlefield = [
            {"id": "wall_of_stone_001", "tapped": False, "keywords": ["defender"]},
            {"id": "serra_angel_001", "tapped": False, "keywords": ["flying", "vigilance"]},
        ]

        mock_socket2 = MagicMock()
        mock_bob = ConnectedClient(mock_socket2, ("127.0.0.1", 12346))
        mock_bob.pid = "bob"
        mock_bob.life_total = 20
        mock_bob.graveyard = []
        mock_bob.hand = []
        mock_bob.library = []
        mock_bob.battlefield = []


        self.mock_connection.clients = [client, mock_bob]
        self.game.clients = self.mock_connection.clients
        self.game.active_player = "alice"
        self.game.phase = "DECLARE_ATTACKERS"

        # Defender cannot attack
        accepted = dispatcher.handle_declare_attackers(client, {
            "type": "DECLARE_ATTACKERS",
            "seq_num": 10,
            "attackers": [{"creature_id": "wall_of_stone_001", "target": "bob"}],
        })
        self.assertFalse(accepted)

        # Serra Angel attacks with Vigilance (should not tap)
        accepted = dispatcher.handle_declare_attackers(client, {
            "type": "DECLARE_ATTACKERS",
            "seq_num": 10,
            "attackers": [{"creature_id": "serra_angel_001", "target": "bob"}],
        })
        self.assertTrue(accepted)
        self.assertFalse(client.battlefield[1]["tapped"])

    def test_play_land_mtgnp_spec_behavior(self):
        """
        Regression test proving MTGNP Section 7.5 behavior:
        Playing a land requires active player, main phase, empty stack, and valid land in hand,
        but does NOT independently require priority_holder == client.pid.
        """
        dispatcher = self.game.pdu_dispatcher
        mock_socket1 = MagicMock()
        client = ConnectedClient(mock_socket1, ("127.0.0.1", 12345))
        client.pid = "alice"
        client.seq_num = 5
        client.hand = ["mountain_001"]
        client.library = []
        client.battlefield = []
        client.life_total = 20
        client.graveyard = []


        mock_socket2 = MagicMock()
        mock_bob = ConnectedClient(mock_socket2, ("127.0.0.1", 12346))
        mock_bob.pid = "bob"
        mock_bob.life_total = 20
        mock_bob.graveyard = []
        mock_bob.hand = []
        mock_bob.library = []
        mock_bob.battlefield = []


        self.mock_connection.clients = [client, mock_bob]
        self.game.clients = self.mock_connection.clients
        self.game.active_player = "alice"
        self.game.phase = "PRECOMBAT_MAIN"
        self.game.priority_holder = None  # Priority holder is NOT alice
        self.game.stack = []

        accepted = dispatcher.handle_play_land(client, {
            "type": "PLAY_LAND",
            "seq_num": 5,
            "card_id": "mountain_001",
        })
        self.assertTrue(accepted)
        self.assertEqual(len(client.battlefield), 1)
        self.assertEqual(client.battlefield[0]["id"], "mountain_001")


if __name__ == "__main__":
    unittest.main()
