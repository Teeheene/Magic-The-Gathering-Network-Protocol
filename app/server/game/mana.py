from typing import Dict, Any, List, Optional, Tuple
from app.server.game.game_state import GameState
from app.server.game.cards import CardCatalog

class ManaPayment:
    COLOR_MAP = {
        "mountain": "R",
        "forest": "G",
        "plains": "W",
        "island": "U",
        "swamp": "B",
        "llanowar_elves": "G",
        "elvish_mystic": "G",
        "sol_ring": "C"
    }

    @staticmethod
    def calculate_cost_requirements(mana_cost: Dict[str, int]) -> Tuple[Dict[str, int], int]:
        colored_reqs = {
            "W": mana_cost.get("W", 0),
            "U": mana_cost.get("U", 0),
            "B": mana_cost.get("B", 0),
            "R": mana_cost.get("R", 0),
            "G": mana_cost.get("G", 0)
        }
        generic_req = mana_cost.get("Generic", 0) + mana_cost.get("X", 0)
        return colored_reqs, generic_req

    @classmethod
    def find_available_mana_sources(cls, player_id: str, game_state: GameState) -> List[Dict[str, Any]]:
        catalog = CardCatalog.get_instance()
        sources: List[Dict[str, Any]] = []
        
        for perm in game_state.battlefield.get(player_id, []):
            if perm.get("tapped", False):
                continue
            card_id = perm.get("id", "")
            base_id = catalog.extract_base_id(card_id)
            color_produced = cls.COLOR_MAP.get(base_id)
            if color_produced:
                if base_id == "sol_ring":
                    # Sol Ring produces 2 colorless
                    sources.append({"id": card_id, "produces": "C", "amount": 2, "perm": perm})
                else:
                    sources.append({"id": card_id, "produces": color_produced, "amount": 1, "perm": perm})
        return sources

    @classmethod
    def can_pay_mana(cls, player_id: str, mana_cost: Dict[str, int], mana_payment: Dict[str, int], game_state: GameState) -> Tuple[bool, str]:
        colored_reqs, generic_req = cls.calculate_cost_requirements(mana_cost)
        
        # Check provided payment matches cost requirements
        for color, req in colored_reqs.items():
            paid = mana_payment.get(color, 0)
            if paid < req:
                return False, f"Insufficient {color} mana declared in payment. Required {req}, got {paid}."

        total_paid_colored = sum(mana_payment.get(c, 0) for c in ["W", "U", "B", "R", "G"])
        total_req_colored = sum(colored_reqs.values())
        excess_colored = total_paid_colored - total_req_colored
        paid_generic = mana_payment.get("X", 0) + mana_payment.get("Generic", 0) + excess_colored

        if paid_generic < generic_req:
            return False, f"Insufficient generic mana declared in payment. Required {generic_req}, got {paid_generic}."

        # Check available sources in game state
        sources = cls.find_available_mana_sources(player_id, game_state)
        needed = dict(colored_reqs)
        needed_generic = generic_req

        used_sources: List[Dict[str, Any]] = []
        
        # Satisfy colored first
        for color, count in list(needed.items()):
            while count > 0:
                found = False
                for src in sources:
                    if src["id"] not in [u["id"] for u in used_sources] and src["produces"] == color:
                        used_sources.append(src)
                        count -= 1
                        found = True
                        break
                if not found:
                    return False, f"Not enough untapped {color} sources available on battlefield."
            needed[color] = 0

        # Satisfy generic from remaining sources
        remaining_sources = [s for s in sources if s["id"] not in [u["id"] for u in used_sources]]
        available_generic_capacity = sum(s["amount"] for s in remaining_sources)

        if available_generic_capacity < needed_generic:
            return False, f"Not enough untapped sources for generic mana cost {generic_req}."

        return True, ""

    @classmethod
    def execute_payment(cls, player_id: str, mana_cost: Dict[str, int], mana_payment: Dict[str, int], game_state: GameState) -> Tuple[bool, str, List[str]]:
        can_pay, msg = cls.can_pay_mana(player_id, mana_cost, mana_payment, game_state)
        if not can_pay:
            return False, msg, []

        colored_reqs, generic_req = cls.calculate_cost_requirements(mana_cost)
        sources = cls.find_available_mana_sources(player_id, game_state)

        tapped_ids: List[str] = []
        needed = dict(colored_reqs)

        # Tap for colored
        for color, count in list(needed.items()):
            while count > 0:
                for src in sources:
                    if src["id"] not in tapped_ids and src["produces"] == color:
                        src["perm"]["tapped"] = True
                        tapped_ids.append(src["id"])
                        count -= 1
                        break

        # Tap for generic
        rem_generic = generic_req
        for src in sources:
            if rem_generic <= 0:
                break
            if src["id"] not in tapped_ids:
                src["perm"]["tapped"] = True
                tapped_ids.append(src["id"])
                rem_generic -= src["amount"]

        return True, "Payment executed", tapped_ids
