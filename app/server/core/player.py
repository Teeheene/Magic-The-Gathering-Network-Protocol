import socket
import json
import struct

class Player:
    def __init__(self, idx, conn):
        self.idx = idx
        self.conn = conn

    def send(self, data):
        if isinstance(data, str):
            pdu = {"type": "NOTIFICATION", "message": data}
        elif isinstance(data, dict):
            pdu = data
        else:
            pdu = {"type": "NOTIFICATION", "message": str(data)}
        
        payload = json.dumps(pdu).encode("utf-8")
        header = struct.pack(">I", len(payload))
        self.conn.sendall(header + payload)



