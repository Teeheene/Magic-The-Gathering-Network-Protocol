import socket
import json
import struct
import sys
from typing import Dict, Any, List, Optional

class ClientState:
    def __init__(self):
        self.player_id: str = ""
        self.last_seq_num: int = 0
        self.current_state: Dict[str, Any] = {}
        self.last_error: Optional[Dict[str, Any]] = None
        self.is_game_over: bool = False
        self.game_over_info: Optional[Dict[str, Any]] = None

    def update_authoritative_state(self, pdu: Dict[str, Any]) -> None:
        if pdu.get("type") == "GAME_STATE_UPDATE":
            self.last_seq_num = pdu.get("seq_num", self.last_seq_num)
            # Full replacement of local view state!
            self.current_state = pdu.get("state", {})
            self.last_error = None
        elif pdu.get("type") == "PRIORITY_GRANT":
            self.last_seq_num = pdu.get("seq_num", self.last_seq_num)
            if "state" in self.current_state:
                self.current_state["priority_holder"] = pdu.get("player_id")
            else:
                self.current_state["priority_holder"] = pdu.get("player_id")
        elif pdu.get("type") == "PHASE_TRANSITION":
            self.last_seq_num = pdu.get("seq_num", self.last_seq_num)
            self.current_state["phase"] = pdu.get("to_phase")
            self.current_state["active_player"] = pdu.get("active_player")
            self.current_state["turn"] = pdu.get("turn", self.current_state.get("turn", 0))
        elif pdu.get("type") == "ERROR":
            self.last_error = pdu
        elif pdu.get("type") == "GAME_OVER":
            self.last_seq_num = pdu.get("seq_num", self.last_seq_num)
            self.is_game_over = True
            self.game_over_info = pdu

    def render(self) -> str:
        lines: List[str] = []
        lines.append("=================== MTGNP CLIENT VIEW ===================")
        if self.is_game_over and self.game_over_info:
            lines.append(f"*** GAME OVER *** Winner: {self.game_over_info.get('winner_id')} | Reason: {self.game_over_info.get('reason')}")
            return "\n".join(lines)

        if self.last_error:
            lines.append(f"!!! REJECTED ACTION ERROR [{self.last_error.get('code')}]: {self.last_error.get('message')}")

        st = self.current_state
        if not st:
            lines.append("Waiting for game state update...")
            return "\n".join(lines)

        if st.get("phase") == "LOBBY":
            lines.append(f"Phase: LOBBY | Ready Players: {st.get('players_ready')} | Waiting for: {st.get('waiting_for')}")
            return "\n".join(lines)

        lines.append(f"Turn: {st.get('turn')} | Phase: {st.get('phase')} | Active Player: {st.get('active_player')} | Priority Holder: {st.get('priority_holder')}")
        lines.append(f"Life Totals: {st.get('life_totals')}")
        lines.append(f"Library Counts: {st.get('library_counts')}")
        lines.append(f"Hand (Local): {st.get('hand', [])}")
        lines.append(f"Hand Counts (Opponent): {st.get('hand_counts', {})}")
        lines.append(f"Graveyards: {st.get('graveyard', {})}")
        
        bf = st.get("battlefield", {})
        lines.append("Battlefields:")
        for p, perms in bf.items():
            lines.append(f"  [{p}]:")
            for perm in perms:
                if "power" in perm:
                    lines.append(f"    - Creature {perm.get('id')}: P/T={perm.get('power')}/{perm.get('toughness')}, Damage={perm.get('damage')}, Tapped={perm.get('tapped')}, Sick={perm.get('summoning_sick')}")
                else:
                    lines.append(f"    - Permanent {perm.get('id')}: Tapped={perm.get('tapped')}")

        stk = st.get("stack", [])
        lines.append(f"Stack (Bottom -> Top, count={len(stk)}):")
        for idx, item in enumerate(stk):
            lines.append(f"  [{idx}] ID: {item.get('stack_item_id')} | Type: {item.get('item_type')} | Source: {item.get('source')} | Controller: {item.get('controller')} | Targets: {item.get('targets')}")

        if self.last_error:
            lines.append(f"!!! REJECTED ACTION ERROR [{self.last_error.get('code')}]: {self.last_error.get('message')}")

        lines.append("=========================================================")
        return "\n".join(lines)

    def build_priority_pass(self) -> Dict[str, Any]:
        return {"type": "PRIORITY_PASS", "seq_num": self.last_seq_num}

    def build_cast_spell(self, card_id: str, targets: List[str], mana_payment: Dict[str, int]) -> Dict[str, Any]:
        return {
            "type": "CAST_SPELL",
            "seq_num": self.last_seq_num,
            "card_id": card_id,
            "targets": targets,
            "mana_payment": mana_payment
        }

    def build_activate_ability(self, source_id: str, ability_index: int, targets: List[str], cost_payment: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "type": "ACTIVATE_ABILITY",
            "seq_num": self.last_seq_num,
            "source_id": source_id,
            "ability_index": ability_index,
            "targets": targets,
            "cost_payment": cost_payment
        }

    def build_play_land(self, card_id: str) -> Dict[str, Any]:
        return {
            "type": "PLAY_LAND",
            "seq_num": self.last_seq_num,
            "card_id": card_id
        }

    def build_declare_attackers(self, attackers: List[Dict[str, str]]) -> Dict[str, Any]:
        return {
            "type": "DECLARE_ATTACKERS",
            "seq_num": self.last_seq_num,
            "attackers": attackers
        }

    def build_declare_blockers(self, blockers: List[Dict[str, str]]) -> Dict[str, Any]:
        return {
            "type": "DECLARE_BLOCKERS",
            "seq_num": self.last_seq_num,
            "blockers": blockers
        }

    def build_assign_damage_order(self, attacker_id: str, blocker_order: List[str]) -> Dict[str, Any]:
        return {
            "type": "ASSIGN_DAMAGE_ORDER",
            "seq_num": self.last_seq_num,
            "attacker_id": attacker_id,
            "blocker_order": blocker_order
        }

    def build_trigger_order_response(self, ordered_trigger_ids: List[str]) -> Dict[str, Any]:
        return {
            "type": "TRIGGER_ORDER_RESPONSE",
            "seq_num": self.last_seq_num,
            "ordered_trigger_ids": ordered_trigger_ids
        }

    def build_trigger_choice_response(self, trigger_id: str, accept: bool, chosen_target: Optional[str] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "type": "TRIGGER_CHOICE_RESPONSE",
            "seq_num": self.last_seq_num,
            "trigger_id": trigger_id,
            "accept": accept
        }
        if chosen_target is not None:
            payload["chosen_target"] = chosen_target
        return payload

    def build_discard(self, card_ids: List[str]) -> Dict[str, Any]:
        return {
            "type": "DISCARD",
            "seq_num": self.last_seq_num,
            "card_ids": card_ids
        }

    def build_concede(self, player_id: str) -> Dict[str, Any]:
        return {
            "type": "CONCEDE",
            "seq_num": self.last_seq_num,
            "player_id": player_id
        }

def send_framed_pdu(sock: socket.socket, pdu: Dict[str, Any]) -> None:
    payload = json.dumps(pdu).encode("utf-8")
    length = len(payload)
    header = struct.pack(">I", length)
    sock.sendall(header + payload)

def read_framed_pdu(sock: socket.socket) -> Optional[Dict[str, Any]]:
    header = sock.recv(4)
    if not header or len(header) < 4:
        return None
    length = struct.unpack(">I", header)[0]
    data = bytearray()
    while len(data) < length:
        packet = sock.recv(length - len(data))
        if not packet:
            return None
        data.extend(packet)
    return json.loads(data.decode("utf-8"))

def main():
    host = input("Enter host [127.0.0.1]: ").strip() or "127.0.0.1"
    port_str = input("Enter port [4444]: ").strip() or "4444"
    port = int(port_str)

    client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_sock.connect((host, port))

    client_state = ClientState()
    print("Connected to MTGNP server.")

    while True:
        pdu = read_framed_pdu(client_sock)
        if not pdu:
            print("Disconnected from server.")
            break

        client_state.update_authoritative_state(pdu)
        print(client_state.render())

if __name__ == "__main__":
    main()
