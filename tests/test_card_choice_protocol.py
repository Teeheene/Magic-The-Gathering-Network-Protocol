import unittest
from unittest.mock import MagicMock

from app.client.pdu_dispatcher import PduDispatcher as ClientDispatcher
from app.client.state import ClientState
from app.server.connected_client import ConnectedClient
from app.server.game import Game


class CardChoiceFixture(unittest.TestCase):
    def setUp(self):
        connection = MagicMock()
        connection.clients = []
        connection.max_clients = 2
        connection.seq_num = 0
        self.game = Game(connection)
        self.alice = self.make_client("alice", 1001)
        self.bob = self.make_client("bob", 1002)
        connection.clients[:] = [self.alice, self.bob]
        self.game.clients = connection.clients
        self.game.active_player = "alice"
        self.game.priority_holder = "alice"
        self.game.phase = "PRECOMBAT_MAIN"

    @staticmethod
    def make_client(pid, port):
        client = ConnectedClient(MagicMock(), ("127.0.0.1", port))
        client.pid = pid
        client.hand = []
        client.library = []
        client.battlefield = []
        client.graveyard = []
        client.exile = []
        client.life_total = 20
        client.mana_pool = {}
        client.active_priority_seq_num = 10
        return client

    def request(self, continuation=None):
        return self.game.pdu_dispatcher.send_card_choice_request(
            self.alice, "test_source_001", "SELECT_CARDS", "Choose one",
            min_choices=1, max_choices=1, options=["a", "b"],
            validator=lambda pdu: pdu.get("selected_cards")
            if pdu.get("selected_cards") in (["a"], ["b"]) else None,
            continuation=continuation,
        )

    def test_client_tracks_independent_choice_token_and_builds_response(self):
        state = ClientState("alice")
        connection = MagicMock()
        dispatcher = ClientDispatcher(state, connection)
        dispatcher.handle({
            "type": "CARD_CHOICE_REQUEST", "seq_num": 50, "player_id": "alice",
            "source_card_id": "x", "choice_type": "YES_NO", "prompt": "?",
            "min_choices": 1, "max_choices": 1, "options": [True, False],
        })
        self.assertEqual(state.card_choice_seq_num, 50)
        self.assertEqual(state.last_received_pdu_seq_num, 50)
        dispatcher.send_card_choice_response(answer=True)
        connection.send.assert_called_with({
            "type": "CARD_CHOICE_RESPONSE", "seq_num": 50,
            "player_id": "alice", "answer": True,
        })

    def test_invalid_response_keeps_original_token_and_corrected_resumes_once(self):
        calls = []
        request = self.request(lambda value: calls.append(value) or True)
        self.assertIsNone(self.game.priority_holder)
        self.assertFalse(self.game.pdu_dispatcher.handle(self.alice, {
            "type": "CARD_CHOICE_RESPONSE", "seq_num": request["seq_num"],
            "player_id": "alice", "selected_cards": ["z"],
        }))
        self.assertEqual(self.alice.active_card_choice_seq_num, request["seq_num"])
        self.assertIsNotNone(self.alice.pending_card_choice)
        self.assertTrue(self.game.pdu_dispatcher.handle(self.alice, {
            "type": "CARD_CHOICE_RESPONSE", "seq_num": request["seq_num"],
            "player_id": "alice", "selected_cards": ["a"],
        }))
        self.assertEqual(calls, [["a"]])
        self.assertIsNone(self.alice.pending_card_choice)

    def test_opponent_cannot_answer_and_gameplay_is_blocked(self):
        request = self.request()
        self.assertFalse(self.game.pdu_dispatcher.handle(self.bob, {
            "type": "CARD_CHOICE_RESPONSE", "seq_num": request["seq_num"],
            "player_id": "bob", "selected_cards": ["a"],
        }))
        self.assertFalse(self.game.pdu_dispatcher.handle(self.alice, {
            "type": "PRIORITY_PASS", "seq_num": 10,
        }))

    def test_ping_allowed_while_choice_pending(self):
        self.request()
        self.assertIsNotNone(self.game.pdu_dispatcher.handle(self.alice, {
            "type": "PING", "seq_num": 7, "timestamp": 1,
        }))


if __name__ == "__main__":
    unittest.main()
