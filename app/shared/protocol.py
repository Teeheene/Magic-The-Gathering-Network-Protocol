import json
import struct
from typing import Any, Optional

HEADER_SIZE = 4
MAX_PAYLOAD_SIZE = 256*256

def recv_exact(sock, size: int) -> bytes:
    data = b""

    while len(data) < size:
        packet = sock.recv(size-len(data))
        if not packet:
            raise ConnectionError("Connection closed.")
        data += packet
    return data 

def encode_pdu(pdu: dict[str, any], verbose: Optional[bool] = False):
    payload = json.dumps(pdu).encode("utf-8")
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise ValueError(
            f"Payload length {len(payload)} exceeds"
            f"maximum allowed ({MAX_PAYLOAD_SIZE})."
        )
    header = struct.pack(">I", len(payload))

    if verbose:
        print("[CLIENT SENT PDU]")
        print(json.dumps(pdu, indent=2))

    return header+payload

def decode_pdu(sock, verbose: Optional[bool] = False) -> dict[str, any]:
    header = recv_exact(sock, HEADER_SIZE)
    length = struct.unpack(">I", header)[0]
    if length > MAX_PAYLOAD_SIZE:
        raise ValueError(
            f"Payload length {length} exceeds"
            f"maximum allowed ({MAX_PAYLOAD_SIZE})."
        )
    payload_bytes = recv_exact(sock, length)

    #validate pdu
    pdu = json.loads(payload_bytes.decode("utf-8"))
    if not isinstance(pdu, dict):
        raise ValueError("PDU must be a JSON object.")
    if not isinstance(pdu.get("type"), str):
        raise ValueError("PDU requires a 'type' field.")
    if not isinstance(pdu.get("seq_num"), int):
        raise ValueError("PDU requires a 'seq_num' field.")

    if verbose:
        print("[CLIENT RECEIVED PDU]")
        print(json.dumps(pdu, indent=2))

    return pdu