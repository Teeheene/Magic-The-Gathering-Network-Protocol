import json
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Union


class Card:
    def __init__(self, card_id: str, data: Dict[str, Any]):
        self.card_id: str = card_id

        self.name: str = data["name"]
        self.card_type: str = data["card_type"]
        self.subtype: Optional[str] = data.get("subtype")
        self.color: Optional[str] = data.get("color")

        self.cmc: int = data.get("cmc", 0)

        self.mana_cost: Dict[str, int] = data.get(
            "mana_cost",
            {
                "W": 0,
                "U": 0,
                "B": 0,
                "R": 0,
                "G": 0,
                "Generic": 0
            }
        )

        self.power: Optional[int] = data.get("power")
        self.toughness: Optional[int] = data.get("toughness")

        self.copies: int = data.get("copies", 0)

        self.text: str = data.get("text", "")
        self.keywords: List[str] = data.get("keywords", [])

    def __repr__(self) -> str:
        return f"<Card {self.name} ({self.card_type})>"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "card_id": self.card_id,
            "name": self.name,
            "card_type": self.card_type,
            "subtype": self.subtype,
            "color": self.color,
            "cmc": self.cmc,
            "mana_cost": self.mana_cost,
            "power": self.power,
            "toughness": self.toughness,
            "copies": self.copies,
            "text": self.text,
            "keywords": self.keywords
        }


class CardCatalog:
    def __init__(self, filepath: Union[str, Path]):
        self.filepath = Path(filepath)
        self.catalog: Dict[str, Dict[str, Any]] = {}

        self.load()

    def load(self) -> None:
        with open(self.filepath, "r", encoding="utf-8") as file:
            self.catalog = json.load(file)

    def create_card(self, card_id: str) -> Card:
        data = self.catalog.get(card_id)

        if data is None:
            raise ValueError(
                f"Card '{card_id}' does not exist in the catalog."
            )

        return Card(card_id, data)

    def get_card_data(self, card_id: str) -> Optional[Dict[str, Any]]:
        return self.catalog.get(card_id)

    def exists(self, card_id: str) -> bool:
        return card_id in self.catalog

    def get_all_card_ids(self) -> List[str]:
        return list(self.catalog.keys())

    def get_all_cards(self) -> List[Card]:
        return [self.create_card(card_id) for card_id in self.catalog]

    def create_copies(self, card_id: str, quantity: int) -> List[Card]:
        """Create a number of cards without exceeding the catalog supply."""
        if isinstance(quantity, bool) or not isinstance(quantity, int):
            raise TypeError("Card quantity must be an integer.")
        if quantity < 1:
            raise ValueError("Card quantity must be at least 1.")

        data = self.get_card_data(card_id)
        if data is None:
            raise ValueError(f"Card '{card_id}' does not exist in the catalog.")

        available = data.get("copies", 0)
        if quantity > available:
            raise ValueError(
                f"Only {available} copies of '{card_id}' are available."
            )

        return [self.create_card(card_id) for _ in range(quantity)]

    def create_deck(self, card_counts: Mapping[str, int]) -> List[Card]:
        """Build a flat list of Card objects from ``card_id: quantity`` pairs."""
        deck: List[Card] = []
        for card_id, quantity in card_counts.items():
            deck.extend(self.create_copies(card_id, quantity))
        return deck

    def print_all_card_ids(self) -> None:
        print("\n====== CARD CATALOG ======")

        for index, card_id in enumerate(self.get_all_card_ids(), start=1):
            card = self.create_card(card_id)

            print(
                f"{index:>2}. "
                f"{card_id:<20} "
                f"| {card.name:<20} "
                f"| {card.card_type}"
            )

        print("==========================\n")
