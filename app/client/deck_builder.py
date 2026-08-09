from pathlib import Path
from typing import Dict, List, Optional

from app.shared.card_catalog import Card, CardCatalog


CATALOG_PATH = Path(__file__).resolve().parents[1] / "shared" / "card_catalog.json"

DEFAULT_DECKS: Dict[str, Dict[str, int]] = {
    "Green": {
        "forest": 20,
        "llanowar_elves": 4,
        "elvish_mystic": 4,
        "grizzly_bears": 4,
        "leatherback_baloth": 4,
        "giant_growth": 4,
    },
    "Red": {
        "mountain": 20,
        "lightning_bolt": 4,
        "shock": 4,
        "lava_spike": 4,
        "goblin_guide": 4,
        "monastery_swiftspear": 4,
    },
    "Blue": {
        "island": 20,
        "counterspell": 4,
        "unsummon": 4,
        "ponder": 4,
        "merfolk_looter": 4,
        "air_elemental": 4,
    },
}


def build_default_deck(cards: CardCatalog, choice: str) -> List[Card]:
    """Return a fresh preset deck made entirely from catalog cards."""
    names = list(DEFAULT_DECKS)
    normalized = choice.strip().casefold()

    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(names):
            normalized = names[index].casefold()

    for name, card_counts in DEFAULT_DECKS.items():
        if normalized == name.casefold():
            return cards.create_deck(card_counts)

    raise ValueError(f"Unknown default deck: {choice}")


def build_custom_deck(cards: CardCatalog) -> List[Card]:
    """Interactively build and return a deck of catalog Card objects."""
    deck: List[Card] = []
    print("Enter a card ID, or 'done' when your deck is complete.")

    while True:
        card_id = input("> > Card ID: ").strip()
        if card_id.casefold() == "done":
            if deck:
                return deck
            print("> > Your deck must contain at least one card.")
            continue

        if not cards.exists(card_id):
            print(f"> > Unknown card ID: {card_id}")
            continue

        try:
            quantity = int(input("> > Quantity: ").strip())
            already_added = sum(card.card_id == card_id for card in deck)
            available = cards.get_card_data(card_id)["copies"]
            if already_added + quantity > available:
                raise ValueError(
                    f"Only {available} copies of '{card_id}' are available."
                )
            deck.extend(cards.create_copies(card_id, quantity))
            print(f"> > Added {quantity} x {card_id} ({len(deck)} cards total).")
        except (TypeError, ValueError) as error:
            print(f"> > {error}")


def choose_deck(cards: Optional[CardCatalog] = None) -> List[Card]:
    cards = cards if cards is not None else CardCatalog(CATALOG_PATH)

    while True:
        command = input("> Customize Deck (Y/N)? ").strip().casefold()
        if command == "n":
            names = list(DEFAULT_DECKS)
            print("> > Decks Available: " + ", ".join(names))
            while True:
                choice = input("> > Choose a default deck (name or number): ")
                try:
                    return build_default_deck(cards, choice)
                except ValueError as error:
                    print(f"> > {error}")
        if command == "y":
            show_cards = input("> > Display all cards? (Y/N)? ").strip().casefold()
            if show_cards == "y":
                cards.print_all_card_ids()
            return build_custom_deck(cards)
        print("> Please enter Y or N.")
