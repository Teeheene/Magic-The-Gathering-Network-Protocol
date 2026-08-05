import unittest
import socket
import threading
import json
import struct
from app.shared.cards import CardCatalog
from app.client.state import ClientState
from app.client.actions import ClientActionFactory
from app.client.transport import ClientTransport
from app.client.cli import run_cli
from app.client.gui import GraphicalGameClient

class TestClientCore(unittest.TestCase):
    def test_shared_card_catalog_loads(self):
        cat = CardCatalog.get_instance()
        self.assertIsNotNone(cat.get_definition("mountain_001"))
        self.assertTrue(cat.is_legal_card("grizzly_bears_001"))

    def test_match_start_assigns_player_id(self):
        st = ClientState()
        st.update_authoritative_state({"type": "MATCH_START", "player_id": "player_2", "seq_num": 1})
        self.assertEqual(st.player_id, "player_2")
        self.assertEqual(st.last_seq_num, 1)

    def test_game_state_update_replaces_authoritative_state(self):
        st = ClientState()
        pdu = {
            "type": "GAME_STATE_UPDATE",
            "seq_num": 5,
            "state": {"phase": "PRECOMBAT_MAIN", "turn": 2}
        }
        st.update_authoritative_state(pdu)
        self.assertEqual(st.last_seq_num, 5)
        self.assertEqual(st.current_state["phase"], "PRECOMBAT_MAIN")

    def test_player_ready_framed_and_transmitted(self):
        server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_sock.bind(("127.0.0.1", 0))
        host, port = server_sock.getsockname()
        server_sock.listen(1)

        received_pdus = []

        def accept_server():
            conn, _ = server_sock.accept()
            hdr = conn.recv(4)
            if hdr:
                length = struct.unpack(">I", hdr)[0]
                data = conn.recv(length)
                received_pdus.append(json.loads(data.decode("utf-8")))
            conn.close()

        th = threading.Thread(target=accept_server, daemon=True)
        th.start()

        transport = ClientTransport()
        transport.connect(host, port)
        
        st = ClientState()
        st.last_seq_num = 10
        ready_pdu = st.build_player_ready("mono_red")
        transport.send_pdu(ready_pdu)

        th.join(timeout=2.0)
        transport.close()
        server_sock.close()

        self.assertEqual(len(received_pdus), 1)
        self.assertEqual(received_pdus[0]["type"], "PLAYER_READY")
        self.assertEqual(received_pdus[0]["seq_num"], 10)
        self.assertEqual(received_pdus[0]["deck_name"], "mono_red")

    def test_tkinter_client_initialization(self):
        app = GraphicalGameClient(client_state=ClientState())
        self.assertIn("MTGNP", app.title())
        app.destroy()

if __name__ == "__main__":
    unittest.main()
