import json
import struct
from typing import Any, Dict, Optional

HEADER_SIZE = 4
MAX_PAYLOAD_SIZE = 65535


def recv_exact(sock, size: int) -> bytes:
    data = b""
    while len(data) < size:
        packet = sock.recv(size - len(data))
        if not packet:
            raise ConnectionError("Connection closed.")
        data += packet
    return data


def encode_pdu(
    pdu: Dict[str, Any],
    verbose: Optional[bool] = False,
    label: Optional[str] = "CLIENT SENT PDU",
) -> bytes:
    payload = json.dumps(pdu).encode("utf-8")
    if len(payload) > MAX_PAYLOAD_SIZE:
        raise ValueError(
            f"Payload length {len(payload)} exceeds maximum allowed ({MAX_PAYLOAD_SIZE})."
        )
    header = struct.pack(">I", len(payload))

    if verbose:
        print(f"[{label or 'SENT PDU'}]")
        print(json.dumps(pdu, indent=2))

    return header + payload


def decode_pdu(
    sock,
    verbose: Optional[bool] = False,
    label: Optional[str] = "CLIENT RECEIVED PDU",
) -> Dict[str, Any]:
    header = recv_exact(sock, HEADER_SIZE)
    length = struct.unpack(">I", header)[0]
    if length > MAX_PAYLOAD_SIZE:
        raise ValueError(
            f"Payload length {length} exceeds maximum allowed ({MAX_PAYLOAD_SIZE})."
        )
    payload_bytes = recv_exact(sock, length)

    pdu = json.loads(payload_bytes.decode("utf-8"))
    if not isinstance(pdu, dict):
        raise ValueError("PDU must be a JSON object.")
    if not isinstance(pdu.get("type"), str):
        raise ValueError("PDU requires a 'type' field.")
    if not isinstance(pdu.get("seq_num"), int):
        raise ValueError("PDU requires a 'seq_num' field.")

    if verbose:
        print(f"[{label or 'RECEIVED PDU'}]")
        print(json.dumps(pdu, indent=2))

    return pdu