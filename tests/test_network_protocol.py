import socket
import threading
import time
import unittest

from app.client.transport import ClientTransport
from app.server.network.server import Server


class TestPersistentNetworkLifecycle(unittest.TestCase):
    def test_concede_returns_same_connections_to_lobby(self):
        server = Server(host="127.0.0.1", port=0)
        port = server.sock.getsockname()[1]
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()

        clients = [ClientTransport(), ClientTransport()]
        try:
            clients[0].connect("127.0.0.1", port)
            clients[0].sock.settimeout(1)
            clients[0].send_pdu({
                "type": "PLAYER_READY", "seq_num": 1, "player_id": "alice",
                "deck_list": [f"mountain_{index:03d}" for index in range(1, 9)],
            })
            first_lobby = clients[0].read_pdu()["state"]
            self.assertEqual(first_lobby["phase"], "LOBBY")
            self.assertEqual(first_lobby["waiting_for"], ["player_2"])

            clients[1].connect("127.0.0.1", port)
            clients[1].sock.settimeout(1)
            clients[1].send_pdu({
                "type": "PLAYER_READY", "seq_num": 1, "player_id": "bob",
                "deck_list": [f"island_{index:03d}" for index in range(1, 9)],
            })
            self.assertEqual(clients[1].read_pdu()["state"]["phase"], "LOBBY")

            setup = [clients[0].read_pdu(), clients[1].read_pdu()]
            self.assertEqual([pdu["state"]["phase"] for pdu in setup], ["MULLIGAN", "MULLIGAN"])
            clients[0].send_pdu({"type": "MULLIGAN_CHOICE", "seq_num": setup[0]["seq_num"], "keep": True, "cards_to_bottom": []})
            clients[1].send_pdu({"type": "MULLIGAN_CHOICE", "seq_num": setup[1]["seq_num"], "keep": True, "cards_to_bottom": []})

            latest_alice = self._drain_latest(clients[0])
            self._drain_latest(clients[1])
            self.assertIsNotNone(latest_alice)
            clients[0].send_pdu({
                "type": "CONCEDE", "seq_num": latest_alice["seq_num"], "player_id": "alice",
            })
            self.assertEqual(self._read_until(clients[0], "GAME_OVER")["reason"], "CONCEDE")
            self.assertEqual(self._read_until(clients[1], "GAME_OVER")["winner_id"], "bob")

            # No reconnect: the same socket and same IDs are legal in the new lobby.
            clients[0].send_pdu({"type": "PLAYER_READY", "seq_num": 2, "player_id": "alice", "deck_list": ["forest_001"]})
            lobby = self._read_until(clients[0], "GAME_STATE_UPDATE")
            self.assertEqual(lobby["state"]["phase"], "LOBBY")
            self.assertEqual(lobby["state"]["players_ready"], 1)
        finally:
            for client in clients:
                client.close()
            server.stop()
            thread.join(timeout=1)

    @staticmethod
    def _drain_latest(client):
        latest = None
        client.sock.settimeout(0.1)
        while True:
            try:
                pdu = client.read_pdu()
            except (socket.timeout, TimeoutError):
                break
            if pdu is None:
                break
            latest = pdu
        client.sock.settimeout(1)
        return latest

    @staticmethod
    def _read_until(client, pdu_type):
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            pdu = client.read_pdu()
            if pdu and pdu.get("type") == pdu_type:
                return pdu
        raise AssertionError(f"Did not receive {pdu_type}")


if __name__ == "__main__":
    unittest.main()
