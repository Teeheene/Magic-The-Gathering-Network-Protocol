import socket
import json
import struct
from typing import Any, Dict, List, Optional


class ProtocolDecodeError(ValueError):
    def __init__(self, message: str, recoverable: bool = True):
        super().__init__(message)
        self.recoverable = recoverable

class Player:
    MAX_PAYLOAD_SIZE = 65535

    def __init__(self, idx, conn):
        self.idx = idx
        self.conn = conn
        self.player_id: Optional[str] = None
        self.deck_list: List[str] = []

    def send(self, data):
        if not isinstance(data, dict):
            raise TypeError("Outbound PDU must be a dictionary.")
        pdu = data
        
        payload = json.dumps(pdu).encode("utf-8")
        if len(payload) > self.MAX_PAYLOAD_SIZE:
            raise ValueError("Outbound payload exceeds the maximum allowed size.")
        header = struct.pack(">I", len(payload))
        self.conn.sendall(header + payload)

    def receive(self) -> Optional[Dict[str, Any]]:
        header = self._recv_exact(4)
        if not header:
            return None

        length = struct.unpack(">I", header)[0]
        if length > self.MAX_PAYLOAD_SIZE:
            raise ProtocolDecodeError("Inbound payload exceeds the maximum allowed size.", recoverable=False)

        payload = self._recv_exact(length)
        if payload is None:
            return None
        try:
            pdu = json.loads(payload.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProtocolDecodeError(f"Invalid UTF-8 JSON: {exc}") from exc
        if not isinstance(pdu, dict):
            raise ProtocolDecodeError("Inbound PDU must be a JSON object.")
        return pdu

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def _recv_exact(self, length: int) -> Optional[bytes]:
        data = bytearray()
        while len(data) < length:
            packet = self.conn.recv(length - len(data))
            if not packet:
                return None
            data.extend(packet)
        return bytes(data)



