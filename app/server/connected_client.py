from app.shared.protocol import encode_pdu, decode_pdu

class ConnectedClient:
    def __init__(self, sock, address):
        self.sock = sock
        self.address = address
        self.pid = None

    def send(self, pdu):
        self.sock.sendall(
            encode_pdu(pdu)
        )

    def receive(self):
        return decode_pdu(
            self.sock
        )

    def close(self):
        self.sock.close()