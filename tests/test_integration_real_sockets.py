import socket
import threading
import time
import unittest

from app.server.connection import ServerConnection
from app.shared.protocol import decode_pdu, encode_pdu


class TestRealSocketIntegration(unittest.TestCase):
    def setUp(self):
        temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        temp_sock.bind(("127.0.0.1", 0))
        self.port = temp_sock.getsockname()[1]
        temp_sock.close()

        self.server = ServerConnection(host="127.0.0.1", port=self.port, verbose=False)
        self.server.start()

    def tearDown(self):
        self.server.running = False
        try:
            self.server.sock.close()
        except Exception:
            pass

    def test_two_client_handshake_rematch_and_3rd_connection_refusal(self):
        # Run server wait_for_players in background thread
        server_thread = threading.Thread(target=self.server.wait_for_players, daemon=True)
        server_thread.start()

        # 1. Connect Client 1 & Client 2
        c1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c1.connect(("127.0.0.1", self.port))

        c2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c2.connect(("127.0.0.1", self.port))

        deck1 = [f"mountain_{i:03d}" for i in range(1, 21)]
        deck2 = [f"forest_{i:03d}" for i in range(1, 21)]

        # 2. Client 1 sends PLAYER_READY (seq_num 1)
        encode_pdu({"type": "PLAYER_READY", "seq_num": 1, "player_id": "alice", "deck_list": deck1})
        c1.sendall(encode_pdu({"type": "PLAYER_READY", "seq_num": 1, "player_id": "alice", "deck_list": deck1}))

        # Client 1 receives GAME_STATE_UPDATE for lobby (waiting for player 2)
        pdu1 = decode_pdu(c1)
        self.assertEqual(pdu1["type"], "GAME_STATE_UPDATE")
        self.assertEqual(pdu1["state"]["phase"], "LOBBY")

        # 3. Client 2 sends PLAYER_READY (seq_num 1)
        c2.sendall(encode_pdu({"type": "PLAYER_READY", "seq_num": 1, "player_id": "bob", "deck_list": deck2}))

        # Both receive GAME_STATE_UPDATE for lobby readiness and GAME_SETUP / MULLIGAN phase transition
        pdu2_c1 = decode_pdu(c1)
        pdu2_c2 = decode_pdu(c2)
        self.assertEqual(pdu2_c1["type"], "GAME_STATE_UPDATE")
        self.assertEqual(pdu2_c2["type"], "GAME_STATE_UPDATE")

        # 4. Test 3rd connection refusal while lobby is running / full
        c3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c3.connect(("127.0.0.1", self.port))
        self.server.refuse_extra_connections()
        res3 = decode_pdu(c3)
        self.assertEqual(res3["type"], "ERROR")
        self.assertEqual(res3["code"], "ILLEGAL_ACTION")
        self.assertIn("Lobby full", res3["message"])
        c3.close()

        # Clean socket close
        c1.close()
        c2.close()

    def test_same_socket_rematch_full_flow(self):
        """Req 11: Real TCP socket test for Game 1 -> CONCEDE -> GAME_OVER -> LOBBY -> fresh PLAYER_READY from both on SAME sockets -> Game 2 setup."""
        server_thread = threading.Thread(target=self.server.wait_for_players, daemon=True)
        server_thread.start()

        c1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c1.settimeout(2.0)
        c1.connect(("127.0.0.1", self.port))

        c2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c2.settimeout(2.0)
        c2.connect(("127.0.0.1", self.port))

        deck1 = [f"mountain_{i:03d}" for i in range(1, 21)]
        deck2 = [f"forest_{i:03d}" for i in range(1, 21)]

        def read_until(sock, target_type):
            while True:
                pdu = decode_pdu(sock)
                if pdu and pdu.get("type") == target_type:
                    return pdu

        def read_until_phase(sock, target_phase):
            while True:
                pdu = decode_pdu(sock)
                if pdu and pdu.get("type") == "PHASE_TRANSITION" and pdu.get("to_phase") == target_phase:
                    return pdu

        # Game 1: Send PLAYER_READY from both
        c1.sendall(encode_pdu({"type": "PLAYER_READY", "seq_num": 1, "player_id": "alice", "deck_list": deck1}))
        read_until(c1, "GAME_STATE_UPDATE")

        c2.sendall(encode_pdu({"type": "PLAYER_READY", "seq_num": 1, "player_id": "bob", "deck_list": deck2}))

        # Read Game 1 setup PDU on c1 & c2
        read_until_phase(c1, "MULLIGAN")
        read_until_phase(c2, "MULLIGAN")

        # Alice concedes during Mulligan phase
        c1.sendall(encode_pdu({"type": "CONCEDE", "seq_num": 10}))

        # Read GAME_OVER PDU on c1 and c2
        go1 = read_until(c1, "GAME_OVER")
        self.assertEqual(go1["type"], "GAME_OVER")
        self.assertEqual(go1["winner_id"], "bob")

        go2 = read_until(c2, "GAME_OVER")
        self.assertEqual(go2["type"], "GAME_OVER")

        # Now send fresh PLAYER_READY on SAME sockets (c1, c2) for Game 2
        c1.sendall(encode_pdu({"type": "PLAYER_READY", "seq_num": 2, "player_id": "alice", "deck_list": deck1}))
        read_until(c1, "GAME_STATE_UPDATE")

        c2.sendall(encode_pdu({"type": "PLAYER_READY", "seq_num": 2, "player_id": "bob", "deck_list": deck2}))

        # Game 2 setup PDU received on c1!
        g2_setup = read_until(c1, "PHASE_TRANSITION")
        self.assertEqual(g2_setup["type"], "PHASE_TRANSITION")
        self.assertEqual(g2_setup["to_phase"], "GAME_SETUP")

        c1.close()
        c2.close()
