import socket
import json
import struct
from typing import Dict, Any, Optional
from PySide6.QtCore import QObject, Signal, Slot
from app.client.state import ClientState
from app.client.actions import ClientActionFactory

class ClientConnectionWorker(QObject):
    pdu_received = Signal(dict)
    connected = Signal()
    disconnected = Signal(str)
    transport_error = Signal(str)

    def __init__(self, verbose: bool = False):
        super().__init__()
        self.sock: Optional[socket.socket] = None
        self.verbose = verbose
        self._running = False

    @Slot(str, int)
    def connect_to_server(self, host: str, port: int) -> None:
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((host, port))
            self._running = True
            if self.verbose:
                print(f"[QT CLIENT CONNECTED] {host}:{port}")
            self.connected.emit()
            self._listen_loop()
        except Exception as e:
            self.transport_error.emit(str(e))
            self.disconnected.emit(str(e))

    def _listen_loop(self):
        MAX_PAYLOAD_SIZE = 65535
        while self._running and self.sock:
            try:
                header = self.sock.recv(4)
                if not header or len(header) < 4:
                    self.disconnected.emit("Connection closed by server.")
                    break
                length = struct.unpack(">I", header)[0]
                if length > MAX_PAYLOAD_SIZE:
                    self.transport_error.emit(f"Payload length {length} > max {MAX_PAYLOAD_SIZE}")
                    break

                data = bytearray()
                while len(data) < length:
                    packet = self.sock.recv(length - len(data))
                    if not packet:
                        break
                    data.extend(packet)

                if len(data) < length:
                    self.disconnected.emit("Incomplete packet received.")
                    break

                pdu = json.loads(data.decode("utf-8"))
                if self.verbose:
                    print("[QT CLIENT RECEIVE]")
                    print(json.dumps(pdu, indent=2))
                self.pdu_received.emit(pdu)
            except Exception as e:
                if self._running:
                    self.disconnected.emit(str(e))
                break

    @Slot(dict)
    def send_pdu(self, pdu: dict) -> None:
        if not self.sock:
            self.transport_error.emit("Cannot send PDU: Not connected.")
            return
        try:
            payload = json.dumps(pdu).encode("utf-8")
            header = struct.pack(">I", len(payload))
            self.sock.sendall(header + payload)
            if self.verbose:
                print("[QT CLIENT SEND]")
                print(json.dumps(pdu, indent=2))
        except Exception as e:
            self.transport_error.emit(f"Failed to send PDU: {e}")

    @Slot()
    def close(self):
        self._running = False
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

class ClientController(QObject):
    state_changed = Signal(dict)
    pdu_received = Signal(dict)
    connection_changed = Signal(str) # "connected", "disconnected", "connecting"
    protocol_error = Signal(dict)
    game_over = Signal(dict)
    mulligan_prompt = Signal(dict)
    trigger_prompt = Signal(dict)
    trigger_order_prompt = Signal(dict)
    discard_prompt = Signal(dict)
    damage_order_prompt = Signal(dict)

    request_connect = Signal(str, int)
    request_send_pdu = Signal(dict)

    def __init__(self, verbose: bool = False):
        super().__init__()
        self.state = ClientState()
        self.verbose = verbose
        self.worker = ClientConnectionWorker(verbose=verbose)

        # Wire worker signals
        self.worker.connected.connect(self._on_worker_connected)
        self.worker.disconnected.connect(self._on_worker_disconnected)
        self.worker.transport_error.connect(self._on_worker_transport_error)
        self.worker.pdu_received.connect(self._handle_pdu)

        self.request_connect.connect(self.worker.connect_to_server)
        self.request_send_pdu.connect(self.worker.send_pdu)

    def connect_server(self, host: str, port: int):
        self.connection_changed.emit("connecting")
        self.request_connect.emit(host, port)

    def send_action(self, pdu: dict):
        self.request_send_pdu.emit(pdu)

    def _on_worker_connected(self):
        self.connection_changed.emit("connected")

    def _on_worker_disconnected(self, reason: str):
        self.connection_changed.emit("disconnected")

    def _on_worker_transport_error(self, err: str):
        self.protocol_error.emit({"type": "ERROR", "code": "TRANSPORT_ERROR", "message": err})

    def _handle_pdu(self, pdu: dict):
        self.state.update_authoritative_state(pdu)
        self.pdu_received.emit(pdu)
        
        ptype = pdu.get("type")
        if ptype == "GAME_STATE_UPDATE":
            self.state_changed.emit(self.state.current_state)
        elif ptype == "ERROR":
            self.protocol_error.emit(pdu)
        elif ptype == "GAME_OVER":
            self.game_over.emit(pdu)
        elif ptype == "MULLIGAN_PROMPT":
            self.mulligan_prompt.emit(pdu)
        elif ptype == "TRIGGER_CHOICE":
            self.trigger_prompt.emit(pdu)
        elif ptype == "TRIGGER_ORDER":
            self.trigger_order_prompt.emit(pdu)
        elif ptype == "DISCARD_PROMPT":
            self.discard_prompt.emit(pdu)
        elif ptype == "ASSIGN_DAMAGE_ORDER_PROMPT":
            self.damage_order_prompt.emit(pdu)

        # Trigger general state update for phase changes / priority grants
        if ptype in ("PHASE_TRANSITION", "PRIORITY_GRANT", "MATCH_START", "PLAYER_ASSIGNMENT"):
            self.state_changed.emit(self.state.current_state)
