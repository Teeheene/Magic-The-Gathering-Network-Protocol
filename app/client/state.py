from typing import Dict, Any, Optional, List
from app.client.actions import ClientActionFactory

class ClientState:
    def __init__(self):
        self.player_id: Optional[str] = None
        self.current_state: Dict[str, Any] = {}
        self.last_seq_num: int = 0
        self.last_error: Optional[Dict[str, Any]] = None
        self.is_game_over: bool = False
        self.game_over_info: Optional[Dict[str, Any]] = None

    def update_authoritative_state(self, pdu: Dict[str, Any]) -> None:
        ptype = pdu.get("type")
        if ptype == "MATCH_START":
            if "player_id" in pdu:
                self.player_id = pdu["player_id"]
            if "seq_num" in pdu:
                self.last_seq_num = pdu["seq_num"]
        elif ptype == "PLAYER_ASSIGNMENT":
            if "player_id" in pdu:
                self.player_id = pdu["player_id"]
            if "seq_num" in pdu:
                self.last_seq_num = pdu["seq_num"]
        elif ptype == "GAME_STATE_UPDATE":
            self.last_seq_num = pdu.get("seq_num", self.last_seq_num)
            self.current_state = pdu.get("state", {})
        elif ptype == "ERROR":
            self.last_error = pdu
        elif ptype == "GAME_OVER":
            self.last_seq_num = pdu.get("seq_num", self.last_seq_num)
            self.is_game_over = True
            self.game_over_info = pdu

    def build_player_ready(self, deck_name: str = "default_deck") -> Dict[str, Any]:
        return ClientActionFactory.player_ready(self.last_seq_num, deck_name)

    def build_priority_pass(self) -> Dict[str, Any]:
        return ClientActionFactory.priority_pass(self.last_seq_num)

    def build_play_land(self, card_id: str) -> Dict[str, Any]:
        return ClientActionFactory.play_land(self.last_seq_num, card_id)

    def build_cast_spell(self, card_id: str, targets: Optional[List[str]] = None, cost_payment: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        return ClientActionFactory.cast_spell(self.last_seq_num, card_id, targets, cost_payment)

    def build_activate_ability(self, source_id: str, ability_index: int = 0, targets: Optional[List[str]] = None, cost_payment: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        return ClientActionFactory.activate_ability(self.last_seq_num, source_id, ability_index, targets, cost_payment)

    def build_declare_attackers(self, attackers: List[Dict[str, str]]) -> Dict[str, Any]:
        return ClientActionFactory.declare_attackers(self.last_seq_num, attackers)

    def build_declare_blockers(self, blockers: List[Dict[str, str]]) -> Dict[str, Any]:
        return ClientActionFactory.declare_blockers(self.last_seq_num, blockers)

    def build_assign_damage_order(self, attacker_id: str, blocker_order: List[str]) -> Dict[str, Any]:
        return ClientActionFactory.assign_damage_order(self.last_seq_num, attacker_id, blocker_order)

    def build_mulligan_choice(self, keep: bool, cards_to_bottom: Optional[List[str]] = None) -> Dict[str, Any]:
        return ClientActionFactory.mulligan_choice(self.last_seq_num, keep, cards_to_bottom)

    def build_trigger_choice_response(self, trigger_id: str, accept: bool, chosen_target: Optional[str] = None) -> Dict[str, Any]:
        return ClientActionFactory.trigger_choice_response(self.last_seq_num, trigger_id, accept, chosen_target)

    def build_trigger_order_response(self, ordered_trigger_ids: List[str]) -> Dict[str, Any]:
        return ClientActionFactory.trigger_order_response(self.last_seq_num, ordered_trigger_ids)

    def build_discard(self, card_ids: List[str]) -> Dict[str, Any]:
        return ClientActionFactory.discard(self.last_seq_num, card_ids)

    def build_concede(self) -> Dict[str, Any]:
        return ClientActionFactory.concede(self.last_seq_num)
