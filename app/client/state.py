from typing import Dict, Any, Optional, List, Tuple
from app.client.actions import ClientActionFactory

def build_default_development_deck() -> List[str]:
    deck: List[str] = []
    for i in range(1, 21):
        deck.append(f"mountain_{i:03d}")
    for i in range(1, 5):
        deck.append(f"lightning_bolt_{i:03d}")
    for i in range(1, 5):
        deck.append(f"shock_{i:03d}")
    for i in range(1, 5):
        deck.append(f"goblin_guide_{i:03d}")
    for i in range(1, 5):
        deck.append(f"searing_spear_{i:03d}")
    for i in range(1, 5):
        deck.append(f"incinerate_{i:03d}")
    return deck

def validate_deck(deck_list: List[str]) -> Tuple[bool, str]:
    if not (1 <= len(deck_list) <= 50):
        return False, f"Deck length {len(deck_list)} is invalid. Must be between 1 and 50."
    if len(set(deck_list)) != len(deck_list):
        return False, "Duplicate card instance IDs found in deck list."
    
    try:
        from app.shared.cards import CardCatalog
        cat = CardCatalog.get_instance()
        for cid in deck_list:
            def_obj = cat.get_definition(cid)
            if not def_obj:
                return False, f"Invalid card instance ID '{cid}' not recognized in catalog."
    except Exception:
        pass
    return True, "Deck is valid."

class ClientState:
    def __init__(self, player_id: Optional[str] = None):
        self.player_id: Optional[str] = player_id
        self.current_state: Dict[str, Any] = {}
        
        self.latest_server_seq_num: int = 0
        self.latest_state_seq_num: int = 0
        self.priority_seq_num: Optional[int] = None
        self.phase_seq_num: Optional[int] = None
        self.trigger_seq_num: Optional[int] = None

        self.last_error: Optional[Dict[str, Any]] = None
        self.is_game_over: bool = False
        self.game_over_info: Optional[Dict[str, Any]] = None

    @property
    def last_seq_num(self) -> int:
        return self.latest_server_seq_num

    @last_seq_num.setter
    def last_seq_num(self, val: int):
        self.latest_server_seq_num = val

    def update_authoritative_state(self, pdu: Dict[str, Any]) -> None:
        ptype = pdu.get("type")
        if "seq_num" in pdu:
            self.latest_server_seq_num = pdu["seq_num"]

        if ptype in ("MATCH_START", "PLAYER_ASSIGNMENT"):
            if "player_id" in pdu and not self.player_id:
                self.player_id = pdu["player_id"]
        elif ptype == "GAME_STATE_UPDATE":
            self.latest_state_seq_num = pdu.get("seq_num", self.latest_state_seq_num)
            self.current_state = pdu.get("state", {})
        elif ptype == "PRIORITY_GRANT":
            self.priority_seq_num = pdu.get("seq_num", self.priority_seq_num)
        elif ptype == "PHASE_TRANSITION":
            self.phase_seq_num = pdu.get("seq_num", self.phase_seq_num)
        elif ptype in ("TRIGGER_ORDER", "TRIGGER_CHOICE"):
            self.trigger_seq_num = pdu.get("seq_num", self.trigger_seq_num)
        elif ptype == "ERROR":
            self.last_error = pdu
        elif ptype == "GAME_OVER":
            self.is_game_over = True
            self.game_over_info = pdu

    def get_local_hand(self) -> List[str]:
        raw_hand = self.current_state.get("hand", {})
        if isinstance(raw_hand, dict):
            if self.player_id and self.player_id in raw_hand:
                return raw_hand[self.player_id]
            for cards in raw_hand.values():
                return cards
            return []
        elif isinstance(raw_hand, list):
            return raw_hand
        return []

    def render(self) -> str:
        if self.last_error:
            err = self.last_error
            return f"[ERROR] Code: {err.get('code')} - Message: {err.get('message')}"

        st = self.current_state
        lines = []
        lines.append(f"Turn {st.get('turn', 1)} | Phase: {st.get('phase', 'UNKNOWN')}")
        lines.append(f"Life Totals: {st.get('life_totals', {})}")
        lines.append(f"Hand Counts: {st.get('hand_counts', {})}")
        lines.append(f"My Hand: {self.get_local_hand()}")
        
        stack = st.get('stack', [])
        if stack:
            lines.append("Stack:")
            for idx, item in enumerate(stack):
                lines.append(f"  [{idx}] ID: {item.get('stack_item_id', '')} Source: {item.get('source', '')}")
        
        return "\n".join(lines)

    def _get_seq(self, preferred: Optional[int]) -> int:
        return preferred if preferred is not None else self.latest_server_seq_num

    def build_player_ready(self, deck_list: Optional[List[str]] = None) -> Dict[str, Any]:
        pid = self.player_id or "player_1"
        dl = deck_list if deck_list is not None else build_default_development_deck()
        return ClientActionFactory.player_ready(self.latest_server_seq_num, pid, dl)

    def build_priority_pass(self) -> Dict[str, Any]:
        return ClientActionFactory.priority_pass(self._get_seq(self.priority_seq_num))

    def build_play_land(self, card_id: str) -> Dict[str, Any]:
        return ClientActionFactory.play_land(self._get_seq(self.priority_seq_num), card_id)

    def build_cast_spell(self, card_id: str, targets: Optional[List[str]] = None, mana_payment: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        return ClientActionFactory.cast_spell(self._get_seq(self.priority_seq_num), card_id, targets, mana_payment)

    def build_activate_ability(self, source_id: str, ability_index: int = 0, targets: Optional[List[str]] = None, cost_payment: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        return ClientActionFactory.activate_ability(self._get_seq(self.priority_seq_num), source_id, ability_index, targets, cost_payment)

    def build_declare_attackers(self, attackers: List[Dict[str, str]]) -> Dict[str, Any]:
        return ClientActionFactory.declare_attackers(self._get_seq(self.phase_seq_num), attackers)

    def build_declare_blockers(self, blockers: List[Dict[str, str]]) -> Dict[str, Any]:
        return ClientActionFactory.declare_blockers(self._get_seq(self.phase_seq_num), blockers)

    def build_assign_damage_order(self, attacker_id: str, blocker_order: List[str]) -> Dict[str, Any]:
        return ClientActionFactory.assign_damage_order(self._get_seq(self.phase_seq_num), attacker_id, blocker_order)

    def build_mulligan_choice(self, keep: bool, cards_to_bottom: Optional[List[str]] = None) -> Dict[str, Any]:
        return ClientActionFactory.mulligan_choice(self._get_seq(self.latest_state_seq_num), keep, cards_to_bottom)

    def build_trigger_choice_response(self, trigger_id: str, accept: bool, chosen_target: Optional[str] = None) -> Dict[str, Any]:
        return ClientActionFactory.trigger_choice_response(self._get_seq(self.trigger_seq_num), trigger_id, accept, chosen_target)

    def build_trigger_order_response(self, ordered_trigger_ids: List[str]) -> Dict[str, Any]:
        return ClientActionFactory.trigger_order_response(self._get_seq(self.trigger_seq_num), ordered_trigger_ids)

    def build_discard(self, card_ids: List[str]) -> Dict[str, Any]:
        return ClientActionFactory.discard(self._get_seq(self.latest_state_seq_num), card_ids)

    def build_concede(self) -> Dict[str, Any]:
        return ClientActionFactory.concede(self.latest_server_seq_num, self.player_id or "player_1")
