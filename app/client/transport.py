import socket
import json
import struct
from typing import Dict, Any, Optional

class ClientTransport:
    MAX_PAYLOAD_SIZE = 65535

    def __init__(self, verbose: bool = False):
        self.sock: Optional[socket.socket] = None
        self.verbose = verbose

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
        header = struct.pack(">I", len(payload))
        self.sock.sendall(header + payload)
        if self.verbose:
            print("[CLIENT SENT PDU]")
            print(json.dumps(pdu, indent=2))

    def read_pdu(self) -> Optional[Dict[str, Any]]:
        if not self.sock:
            return None
        try:
            header = self.sock.recv(4)
            if not header or len(header) < 4:
                return None
            length = struct.unpack(">I", header)[0]
            if length > self.MAX_PAYLOAD_SIZE:
                raise ValueError(f"Payload length {length} exceeds maximum allowed ({self.MAX_PAYLOAD_SIZE}).")
            
            data = bytearray()
            while len(data) < length:
                packet = self.sock.recv(length - len(data))
                if not packet:
                    break
                data.extend(packet)
            
            if len(data) < length:
                return None

            pdu = json.loads(data.decode("utf-8"))
            if self.verbose:
                print("[CLIENT RECEIVED PDU]")
                print(json.dumps(pdu, indent=2))
            return pdu
        except Exception as e:
            if self.verbose:
                print(f"[CLIENT READ ERROR] {e}")
            return None
