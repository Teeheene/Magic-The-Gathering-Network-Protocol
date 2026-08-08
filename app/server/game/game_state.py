from typing import Dict, List, Any, Optional, Set
import app.shared.cards
import copy

class GameState:
    def __init__(self, players: List[str]):
        self.players = list(players)
        self.active_player: str = players[0] if players else ""
        self.priority_holder: Optional[str] = None
        self.phase: str = "LOBBY"
        self.turn: int = 0
        self.life_totals: Dict[str, int] = {p: 20 for p in players}
        self.hands: Dict[str, List[str]] = {p: [] for p in players}
        self.libraries: Dict[str, List[str]] = {p: [] for p in players}
        self.graveyards: Dict[str, List[str]] = {p: [] for p in players}
        self.exile: Dict[str, List[str]] = {p: [] for p in players}
        self.battlefield: Dict[str, List[Dict[str, Any]]] = {p: [] for p in players}
        self.stack: List[Dict[str, Any]] = []
        self.land_played_this_turn: bool = False
        self.temporary_effects: List[Dict[str, Any]] = []
        self.damage_prevention_shields: Dict[str, int] = {}
        self.cant_gain_life: bool = False
        self.cant_prevent_damage: bool = False
        self.decked_players: Set[str] = set()
        self.mana_pools: Dict[str, Dict[str, int]] = {
            p: {color: 0 for color in ("W", "U", "B", "R", "G", "C")} for p in players
        }

    def get_opponent(self, player_id: str) -> str:
        for p in self.players:
            if p != player_id:
                return p
        return ""

    def get_permanent(self, permanent_id: str) -> Optional[Dict[str, Any]]:
        for p in self.players:
            for perm in self.battlefield[p]:
                if perm.get("id") == permanent_id:
                    return perm
        return None

    def get_permanent_controller(self, permanent_id: str) -> Optional[str]:
        for p in self.players:
            for perm in self.battlefield[p]:
                if perm.get("id") == permanent_id:
                    return p
        return None

    def get_personalized_state(self, viewing_player: str) -> Dict[str, Any]:
        state_dict: Dict[str, Any] = {
            "turn": self.turn,
            "active_player": self.active_player,
            "phase": self.phase,
            "priority_holder": self.priority_holder,
            "life_totals": copy.deepcopy(self.life_totals),
            "stack": copy.deepcopy(self.stack),
            "battlefield": copy.deepcopy(self.battlefield),
            "graveyard": copy.deepcopy(self.graveyards),
            "hand": {viewing_player: copy.deepcopy(self.hands.get(viewing_player, []))},
            "hand_counts": {p: len(cards) for p, cards in self.hands.items() if p != viewing_player},
            "library_counts": {p: len(cards) for p, cards in self.libraries.items()},
            "land_played_this_turn": self.land_played_this_turn,
            "mana_pools": copy.deepcopy(self.mana_pools),
        }
        return state_dict
