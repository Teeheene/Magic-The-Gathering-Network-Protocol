from typing import Dict, Any, Optional, List

class ClientActionFactory:
    @staticmethod
    def player_ready(seq_num: int, player_id: str, deck_list: List[str]) -> Dict[str, Any]:
        return {
            "type": "PLAYER_READY",
            "seq_num": seq_num,
            "player_id": player_id,
            "deck_list": deck_list
        }

    @staticmethod
    def priority_pass(seq_num: int) -> Dict[str, Any]:
        return {
            "type": "PRIORITY_PASS",
            "seq_num": seq_num
        }

    @staticmethod
    def play_land(seq_num: int, card_id: str) -> Dict[str, Any]:
        return {
            "type": "PLAY_LAND",
            "seq_num": seq_num,
            "card_id": card_id
        }

    @staticmethod
    def cast_spell(seq_num: int, card_id: str, targets: Optional[List[str]] = None, mana_payment: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        return {
            "type": "CAST_SPELL",
            "seq_num": seq_num,
            "card_id": card_id,
            "targets": targets if targets is not None else [],
            "mana_payment": mana_payment if mana_payment is not None else {}
        }

    @staticmethod
    def activate_ability(seq_num: int, source_id: str, ability_index: int = 0, targets: Optional[List[str]] = None, cost_payment: Optional[Dict[str, int]] = None) -> Dict[str, Any]:
        return {
            "type": "ACTIVATE_ABILITY",
            "seq_num": seq_num,
            "source_id": source_id,
            "ability_index": ability_index,
            "targets": targets if targets is not None else [],
            "cost_payment": cost_payment if cost_payment is not None else {}
        }

    @staticmethod
    def declare_attackers(seq_num: int, attackers: List[Dict[str, str]]) -> Dict[str, Any]:
        return {
            "type": "DECLARE_ATTACKERS",
            "seq_num": seq_num,
            "attackers": attackers
        }

    @staticmethod
    def declare_blockers(seq_num: int, blockers: List[Dict[str, str]]) -> Dict[str, Any]:
        return {
            "type": "DECLARE_BLOCKERS",
            "seq_num": seq_num,
            "blockers": blockers
        }

    @staticmethod
    def assign_damage_order(seq_num: int, attacker_id: str, blocker_order: List[str]) -> Dict[str, Any]:
        return {
            "type": "ASSIGN_DAMAGE_ORDER",
            "seq_num": seq_num,
            "attacker_id": attacker_id,
            "blocker_order": blocker_order
        }

    @staticmethod
    def mulligan_choice(seq_num: int, keep: bool, cards_to_bottom: Optional[List[str]] = None) -> Dict[str, Any]:
        pdu: Dict[str, Any] = {
            "type": "MULLIGAN_CHOICE",
            "seq_num": seq_num,
            "keep": keep
        }
        if cards_to_bottom is not None:
            pdu["cards_to_bottom"] = cards_to_bottom
        return pdu

    @staticmethod
    def trigger_choice_response(seq_num: int, trigger_id: str, accept: bool, chosen_target: Optional[str] = None) -> Dict[str, Any]:
        pdu: Dict[str, Any] = {
            "type": "TRIGGER_CHOICE_RESPONSE",
            "seq_num": seq_num,
            "trigger_id": trigger_id,
            "accept": accept
        }
        if chosen_target is not None:
            pdu["chosen_target"] = chosen_target
        return pdu

    @staticmethod
    def trigger_order_response(seq_num: int, ordered_trigger_ids: List[str]) -> Dict[str, Any]:
        return {
            "type": "TRIGGER_ORDER_RESPONSE",
            "seq_num": seq_num,
            "ordered_trigger_ids": ordered_trigger_ids
        }

    @staticmethod
    def discard(seq_num: int, card_ids: List[str]) -> Dict[str, Any]:
        return {
            "type": "DISCARD",
            "seq_num": seq_num,
            "card_ids": card_ids
        }

    @staticmethod
    def concede(seq_num: int, player_id: str) -> Dict[str, Any]:
        return {
            "type": "CONCEDE",
            "seq_num": seq_num,
            "player_id": player_id
        }
