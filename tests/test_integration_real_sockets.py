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
        """Req 6: Real TCP socket test for Game 1 -> MULLIGAN KEEP -> UPKEEP -> CONCEDE -> GAME_OVER -> LOBBY -> fresh PLAYER_READY on SAME sockets -> Game 2."""
        server_thread = threading.Thread(target=self.server.wait_for_players, daemon=True)
        server_thread.start()

        c1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c1.settimeout(3.0)
        c1.connect(("127.0.0.1", self.port))

        c2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c2.settimeout(3.0)
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

        # Game 1: Send PLAYER_READY from both (seed rng so alice is active player)
        import random
        self.server.game.rng = random.Random(1)
        c1.sendall(encode_pdu({"type": "PLAYER_READY", "seq_num": 1, "player_id": "alice", "deck_list": deck1}))
        read_until(c1, "GAME_STATE_UPDATE")

        c2.sendall(encode_pdu({"type": "PLAYER_READY", "seq_num": 1, "player_id": "bob", "deck_list": deck2}))

        # Read Game 1 MULLIGAN phase transitions and state updates
        read_until_phase(c1, "MULLIGAN")
        read_until_phase(c2, "MULLIGAN")
        gsu_c1 = read_until(c1, "GAME_STATE_UPDATE")
        gsu_c2 = read_until(c2, "GAME_STATE_UPDATE")

        # Both keep hand in Mulligan
        c1.sendall(encode_pdu({"type": "MULLIGAN_CHOICE", "seq_num": gsu_c1["seq_num"], "keep": True, "cards_to_bottom": []}))
        c2.sendall(encode_pdu({"type": "MULLIGAN_CHOICE", "seq_num": gsu_c2["seq_num"], "keep": True, "cards_to_bottom": []}))

        # Both reach UPKEEP
        upk_c1 = read_until_phase(c1, "UPKEEP")
        upk_c2 = read_until_phase(c2, "UPKEEP")

        # Alice receives priority in UPKEEP and concedes using the latest server token
        pg_c1 = read_until(c1, "PRIORITY_GRANT")
        c1.sendall(encode_pdu({"type": "CONCEDE", "seq_num": pg_c1["seq_num"], "player_id": "alice"}))

        # Read GAME_OVER PDU on c1 and c2
        go1 = read_until(c1, "GAME_OVER")
        self.assertEqual(go1["type"], "GAME_OVER")
        self.assertEqual(go1["winner_id"], "bob")

        go2 = read_until(c2, "GAME_OVER")
        self.assertEqual(go2["type"], "GAME_OVER")

        # Both receive LOBBY game state update after match reset
        l_c1 = read_until(c1, "GAME_STATE_UPDATE")
        self.assertEqual(l_c1["state"]["phase"], "LOBBY")
        l_c2 = read_until(c2, "GAME_STATE_UPDATE")
        self.assertEqual(l_c2["state"]["phase"], "LOBBY")

        # Now send fresh PLAYER_READY on SAME sockets (c1, c2) for Game 2
        c1.sendall(encode_pdu({"type": "PLAYER_READY", "seq_num": 2, "player_id": "alice", "deck_list": deck1}))
        c2.sendall(encode_pdu({"type": "PLAYER_READY", "seq_num": 2, "player_id": "bob", "deck_list": deck2}))
        time.sleep(0.1)

        # Game 2 setup PDU received on c1!
        g2_setup = read_until_phase(c1, "GAME_SETUP")
        self.assertEqual(g2_setup["type"], "PHASE_TRANSITION")
        self.assertEqual(g2_setup["to_phase"], "GAME_SETUP")

        c1.close()
        c2.close()

    def test_lobby_malformed_json_resilience(self):
        """Item 9: Server receives malformed JSON in lobby -> sends INVALID_JSON error -> connection stays alive -> accepts valid PLAYER_READY."""
        server_thread = threading.Thread(target=self.server.wait_for_players, daemon=True)
        server_thread.start()

        c1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c1.settimeout(2.0)
        c1.connect(("127.0.0.1", self.port))
        time.sleep(0.05)

        # Send framed malformed JSON bytes (header = 4, payload = 4 bytes '{bad')
        raw_invalid = b"\x00\x00\x00\x04{bad"
        c1.sendall(raw_invalid)

        # Server sends INVALID_JSON error PDU
        err_pdu = decode_pdu(c1)
        self.assertEqual(err_pdu["type"], "ERROR")
        self.assertEqual(err_pdu["code"], "INVALID_JSON")

        # Server thread stays alive and accepts valid PLAYER_READY on same connection
        deck1 = [f"mountain_{i:03d}" for i in range(1, 21)]
        c1.sendall(encode_pdu({"type": "PLAYER_READY", "seq_num": 1, "player_id": "alice", "deck_list": deck1}))

        res_pdu = decode_pdu(c1)
        self.assertEqual(res_pdu["type"], "GAME_STATE_UPDATE")
        self.assertEqual(res_pdu["state"]["phase"], "LOBBY")

        c1.close()
