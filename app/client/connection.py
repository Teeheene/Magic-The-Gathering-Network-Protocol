import socket
import threading
from typing import Optional
from app.shared.protocol import encode_pdu, decode_pdu 


class ClientConnection:
    def __init__(self, 
                 host: str = "127.0.0.1", 
                 port: int = 4444, 
                 verbose: Optional[bool] = False):
        self.host = host
        self.port = port
        self.verbose = verbose

        self.username = None
        self.player_id = None
        self.joined = False

        self.sock = None
        self.running = False

        #server info
        self.latest_seq_num = 1
        self.priority_seq_num = 1

    def connect(self):
        #initialize connections
        self.sock = socket.socket(
            socket.AF_INET, 
            socket.SOCK_STREAM
        )
        self.sock.connect(
            (self.host, self.port)
        )
        self.running = True

        #thread client connections
        thread = threading.Thread(
            target=self.listen,
            daemon=True
        )
        thread.start()

    def join_lobby(self, username):
        self.send({
            "type": "PLAYER_READY",
            "seq_num": self.latest_seq_num,
            "username": username
        })

    def listen(self):
        while self.running:
            try:
                pdu = self.receive()
                self.handle(pdu)
            except ConnectionError:
                print("Server Disconnected.")
                self.running = False
        
    def send(self, pdu):
        if not self.sock:
            raise RuntimeError(
                "Cannot send PDU: socket not connected."
            )
        self.sock.sendall(encode_pdu(pdu, self.verbose))

    def receive(self):
        return decode_pdu(self.sock, self.verbose) 

    def handle(self, pdu):
        print("SERVER: ", pdu)

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass