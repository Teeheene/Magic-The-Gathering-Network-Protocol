import socket
import threading
import time
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
        self.sock = None
        self.running = False
        self.pdu_handler = None
        self.ping_interval = 30.0
        self.pong_timeout = 30.0

    def connect(self):
        self.sock = socket.socket(
            socket.AF_INET, 
            socket.SOCK_STREAM
        )
        self.sock.connect(
            (self.host, self.port)
        )
        self.running = True

        thread = threading.Thread(
            target=self.listen,
            daemon=True
        )
        thread.start()

    def start_heartbeat(self, dispatcher, ping_interval: float = 30.0, pong_timeout: float = 30.0):
        """Start a background daemon thread that sends PING and verifies PONG correlation & timeout."""
        self.ping_interval = ping_interval
        self.pong_timeout = pong_timeout
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(dispatcher,),
            daemon=True
        )
        heartbeat_thread.start()

    def _heartbeat_loop(self, dispatcher):
        dispatcher.state.last_pong_timestamp = time.time()
        while self.running:
            time.sleep(self.ping_interval)
            if not self.running:
                break

            try:
                dispatcher.send_ping()
            except Exception:
                self.close()
                break

            start_wait = time.time()
            while self.running:
                if getattr(dispatcher.state, "pending_ping_seq", None) is None:
                    break
                if time.time() - start_wait >= self.pong_timeout:
                    print("Heartbeat PONG timeout exceeded. Closing connection.")
                    self.close()
                    return
                time.sleep(0.05)


    def listen(self):
        while self.running:
            try:
                pdu = self.receive()
                if self.pdu_handler is not None:
                    self.pdu_handler(pdu)
            except ValueError as error:
                print(f"Invalid server PDU: {error}")
            except (ConnectionError, OSError):
                print("Server Disconnected.")
                self.running = False
                break
        
    def send(self, pdu):
        if not self.sock:
            raise RuntimeError(
                "Cannot send PDU: socket not connected."
            )
        self.sock.sendall(encode_pdu(pdu, self.verbose))

    def receive(self):
        return decode_pdu(self.sock, self.verbose) 

    def close(self):
        self.running = False
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
