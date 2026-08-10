from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class CardViewData:
    card_id: str
    name: str
    mana_cost: str = ""
    card_type: str = ""
    rules_text: str = ""
    power_toughness: str = ""
    tapped: bool = False
    selected: bool = False
    selectable: bool = True
    highlighted: bool = False
    combat_role: str = ""


class GamePresenter:
    """Pure state-to-display adapter; it never sends actions or mutates the server."""

    def __init__(self, state, catalog):
        self.state = state
        self.catalog = catalog

    def card(self, card_id, **flags) -> CardViewData:
        data = self.catalog.get_card_data(card_id) or {}
        cost = data.get("mana_cost", {})
        cost_text = " ".join(
            (str(amount) + color) for color, amount in cost.items() if amount
        )
        pt = ""
        if data.get("power") is not None:
            pt = f"{data.get('power')}/{data.get('toughness')}"
        return CardViewData(
            card_id=card_id,
            name=data.get("name", card_id),
            mana_cost=cost_text,
            card_type=data.get("card_type", ""),
            rules_text=data.get("text", ""),
            power_toughness=pt,
            **flags,
        )

    def battlefield(self, pid) -> List[CardViewData]:
        return [
            self.card(p.get("id", str(p)), tapped=bool(p.get("tapped")))
            for p in self.state.battlefield.get(pid, [])
        ]

    def opponent_id(self):
        return next((pid for pid in self.state.life_totals if pid != self.state.pid), None)

    def zone_counts(self) -> Dict[str, int]:
        opponent = self.opponent_id()
        return {
            "hand": len(self.state.local_hand),
            "library": self.state.library_counts.get(self.state.pid, 0),
            "graveyard": len(self.state.graveyard.get(self.state.pid, [])),
            "exile": len(self.state.exile.get(self.state.pid, [])),
            "opponent_hand": self.state.hand_counts.get(opponent, 0),
            "opponent_library": self.state.library_counts.get(opponent, 0),
        }
