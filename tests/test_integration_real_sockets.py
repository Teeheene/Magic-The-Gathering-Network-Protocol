import socket
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

    def test_two_client_handshake_and_3rd_connection_refusal(self):
        # Test server socket acceptance & connection refusal in non-blocking fashion
        self.server.sock.settimeout(0.1)

        c1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c1.connect(("127.0.0.1", self.port))

        client_sock, addr = self.server.sock.accept()
        self.assertIsNotNone(client_sock)

        c2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c2.connect(("127.0.0.1", self.port))

        client_sock2, addr2 = self.server.sock.accept()
        self.assertIsNotNone(client_sock2)

        c3 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        c3.connect(("127.0.0.1", self.port))

        # Test active 3rd connection refusal
        self.server.refuse_extra_connections()
        res3 = decode_pdu(c3)
        self.assertEqual(res3["type"], "ERROR")
        self.assertEqual(res3["code"], "ILLEGAL_ACTION")
        self.assertIn("Lobby full", res3["message"])

        c1.close()
        c2.close()
        c3.close()
        client_sock.close()
        client_sock2.close()


if __name__ == "__main__":
    unittest.main()
