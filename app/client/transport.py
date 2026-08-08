import socket
import json
import struct
import threading
from typing import Dict, Any, Optional

def recv_exact(sock: socket.socket, length: int) -> Optional[bytes]:
    data = bytearray()
    while len(data) < length:
        try:
            packet = sock.recv(length - len(data))
            if not packet:
                return None
            data.extend(packet)
        except Exception:
            return None
    return bytes(data)

class ClientTransport:
    MAX_PAYLOAD_SIZE = 65535

    def __init__(self, verbose: bool = False):
        self.sock: Optional[socket.socket] = None
        self.verbose = verbose
        self._send_lock = threading.Lock()

    def connect(self, host: str, port: int) -> None:
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host, port))

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def send_pdu(self, pdu: Dict[str, Any]) -> None:
        if not self.sock:
            raise RuntimeError("Cannot send PDU: socket not connected.")
        payload = json.dumps(pdu).encode("utf-8")
        if len(payload) > self.MAX_PAYLOAD_SIZE:
            raise ValueError(f"Outbound payload length {len(payload)} exceeds maximum allowed ({self.MAX_PAYLOAD_SIZE}).")
        header = struct.pack(">I", len(payload))
        with self._send_lock:
            self.sock.sendall(header + payload)
        if self.verbose:
            print("[CLIENT SENT PDU]")
            print(json.dumps(pdu, indent=2))

    def read_pdu(self) -> Optional[Dict[str, Any]]:
        if not self.sock:
            return None
        header = recv_exact(self.sock, 4)
        if not header or len(header) < 4:
            return None
        length = struct.unpack(">I", header)[0]
        if length > self.MAX_PAYLOAD_SIZE:
            raise ValueError(f"Inbound payload length {length} exceeds maximum allowed ({self.MAX_PAYLOAD_SIZE}).")

        data_bytes = recv_exact(self.sock, length)
        if not data_bytes or len(data_bytes) < length:
            return None

        pdu = json.loads(data_bytes.decode("utf-8"))
        if not isinstance(pdu, dict):
            raise ValueError("Inbound PDU must be a JSON object.")
        if not isinstance(pdu.get("type"), str) or not isinstance(pdu.get("seq_num"), int):
            raise ValueError("Inbound PDU requires type and seq_num fields.")
        if self.verbose:
            print("[CLIENT RECEIVED PDU]")
            print(json.dumps(pdu, indent=2))
        return pdu
