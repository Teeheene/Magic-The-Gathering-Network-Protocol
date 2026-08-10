from typing import Optional
from app.shared.protocol import decode_pdu, encode_pdu


class ConnectedClient:
    def __init__(self, sock, address, verbose: Optional[bool] = False):
        self.sock = sock
        self.address = address
        self.verbose = verbose
        self.pid = None

        self.mulligan_taken = 0
        self.mulligan_kept = False

        self.active_priority_seq_num = None
        self.active_phase_seq_num = None
        self.active_trigger_seq_num = None
        self.active_mulligan_seq_num = None
        self.active_cleanup_seq_num = None
        self.phase_seq_num = None
        self.pending_trigger_ids = None
        self.pending_trigger_choice = None

    def send(self, pdu):
        self.sock.sendall(
            encode_pdu(pdu, verbose=self.verbose, label="SERVER SENT PDU")
        )

    def receive(self):
        return decode_pdu(
            self.sock, verbose=self.verbose, label="SERVER RECEIVED PDU"
        )

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass