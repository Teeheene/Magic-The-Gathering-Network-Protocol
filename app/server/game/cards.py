import json
import os
import re
from typing import Dict, Any, Optional, List

class CardDefinition:
    def __init__(self, base_id: str, data: Dict[str, Any]):
        self.base_id = base_id
        self.name: str = data["name"]
        self.card_type: str = data["card_type"]
        self.subtype: str = data.get("subtype", "")
        self.color: str = data.get("color", "")
        self.cmc: int = data.get("cmc", 0)
        self.mana_cost: Dict[str, int] = data.get("mana_cost", {})
        self.power: Optional[int] = data.get("power")
        self.toughness: Optional[int] = data.get("toughness")
        self.copies: int = data.get("copies", 4)
        self.text: str = data.get("text", "")
        self.keywords: List[str] = data.get("keywords", [])

    def is_land(self) -> bool:
        return "Land" in self.card_type

    def is_creature(self) -> bool:
        return "Creature" in self.card_type

    def is_instant(self) -> bool:
        return "Instant" in self.card_type

    def is_sorcery(self) -> bool:
        return "Sorcery" in self.card_type

    def is_permanent(self) -> bool:
        return self.is_land() or self.is_creature() or "Artifact" in self.card_type or "Enchantment" in self.card_type

class CardInstance:
    def __init__(self, card_id: str, definition: CardDefinition, owner: str):
        self.card_id = card_id
        self.definition = definition
        self.owner = owner
        self.controller = owner
        self.zone = "library"
        self.tapped = False
        self.damage = 0
        self.summoning_sick = definition.is_creature() and ("haste" not in definition.keywords)
        self.temp_power_mod = 0
        self.temp_toughness_mod = 0
        self.temp_keywords: List[str] = []
        self.attached_to: Optional[str] = None # e.g. Pacifism target

    @property
    def current_power(self) -> int:
        base = self.definition.power or 0
        return max(0, base + self.temp_power_mod)

    @property
    def current_toughness(self) -> int:
        base = self.definition.toughness or 0
        return base + self.temp_toughness_mod

    @property
    def all_keywords(self) -> List[str]:
        return list(set(self.definition.keywords + self.temp_keywords))

    def to_battlefield_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "id": self.card_id,
            "tapped": self.tapped
        }
        if self.definition.is_creature():
            d.update({
                "damage": self.damage,
                "power": self.current_power,
                "toughness": self.current_toughness,
                "summoning_sick": self.summoning_sick
            })
        return d

class CardCatalog:
    _instance: Optional['CardCatalog'] = None

    def __init__(self, catalog_path: Optional[str] = None):
        if catalog_path is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            catalog_path = os.path.normpath(os.path.join(base_dir, "..", "..", "shared", "card_catalog.json"))
        
        with open(catalog_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
            
        self.definitions: Dict[str, CardDefinition] = {
            base_id: CardDefinition(base_id, data)
            for base_id, data in raw_data.items()
        }

    @classmethod
    def get_instance(cls) -> 'CardCatalog':
        if cls._instance is None:
            cls._instance = CardCatalog()
        return cls._instance

    def extract_base_id(self, card_id: str) -> str:
        # e.g., "lightning_bolt_001" -> "lightning_bolt"
        m = re.match(r"^(.*?)(?:_\d{3})?$", card_id)
        if m and m.group(1) in self.definitions:
            return m.group(1)
        return card_id

    def get_definition(self, card_id: str) -> Optional[CardDefinition]:
        base_id = self.extract_base_id(card_id)
        return self.definitions.get(base_id)

    def is_legal_card(self, card_id: str) -> bool:
        return self.get_definition(card_id) is not None
