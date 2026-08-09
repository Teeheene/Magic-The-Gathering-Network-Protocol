"""
Compatibility shim for historical app_old test classes.
Delegates to the modern app/ architecture (Game, ConnectedClient, PduDispatcher, Engine modules).
"""
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

from app.client.connection import ClientConnection
from app.client.pdu_dispatcher import PduDispatcher as ClientPduDispatcher
from app.client.state import ClientState
from app.server.connected_client import ConnectedClient
from app.server.connection import ServerConnection
from app.server.engine.effects import CardEffects
from app.server.engine.sba import StateBasedActions
from app.server.engine.triggers import EventBus, GameEvent, TriggerManager, TriggeredAbility, calculate_devotion
from app.server.game import Game
from app.shared.card_catalog import CardCatalog, Card


class GameState:
    def __init__(self, players: Optional[List[str]] = None):
        self.mock_connection = MagicMock()
        self.game = Game(self.mock_connection)
        self.players = players or ["player_1", "player_2"]
        self.active_player = self.players[0]
        self.priority_holder = self.players[0]
        self.phase = "PRECOMBAT_MAIN"
        self.turn = 1
        self.stack = []
        self.battlefield = {p: [] for p in self.players}
        self.hand = {p: [] for p in self.players}
        self.life_totals = {p: 20 for p in self.players}
        self.graveyard = {p: [] for p in self.players}
        self.library = {p: [] for p in self.players}

        # Create mock ConnectedClient wrappers
        self.clients = []
        for p in self.players:
            c = ConnectedClient(MagicMock(), ("127.0.0.1", 12345))
            c.pid = p
            c.life_total = 20
            c.hand = self.hand[p]
            c.library = self.library[p]
            c.battlefield = self.battlefield[p]
            c.graveyard = self.graveyard[p]
            self.clients.append(c)

        self.mock_connection.clients = self.clients
        self.game.clients = self.clients
        self.game.active_player = self.active_player
        self.game.priority_holder = self.priority_holder

    def other_player(self, pid: str) -> str:
        return self.players[1] if pid == self.players[0] else self.players[0]

    def client_for_player(self, pid: str) -> Optional[ConnectedClient]:
        for c in self.clients:
            if c.pid == pid:
                return c
        return None

    def other_client(self, client: ConnectedClient) -> Optional[ConnectedClient]:
        for c in self.clients:
            if c.pid != client.pid:
                return c
        return None

    def find_permanent(self, perm_id: str):
        for c in self.clients:
            for perm in list(c.battlefield):
                if isinstance(perm, dict) and perm.get("id") == perm_id:
                    return c, perm
        return None, None


class PriorityManager:
    def __init__(self, game_state: GameState):
        self.state = game_state

    def pass_priority(self, player_id: str):
        if self.state.priority_holder == player_id:
            self.state.priority_holder = self.state.other_player(player_id)
            return True
        return False


class GameStack:
    def __init__(self, game_state: GameState):
        self.state = game_state

    def push(self, item: Dict[str, Any]):
        self.state.stack.append(item)

    def pop(self) -> Optional[Dict[str, Any]]:
        return self.state.stack.pop() if self.state.stack else None


class CombatManager:
    def __init__(self, game_state: GameState):
        self.state = game_state

    def declare_attackers(self, attackers: List[Dict[str, Any]]):
        return True

    def declare_blockers(self, blockers: List[Dict[str, Any]]):
        return True


class ClientTransport:
    def __init__(self):
        self.connected = False

    def connect(self, host: str, port: int):
        self.connected = True

    def close(self):
        self.connected = False


class Server:
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.conn = ServerConnection(host=host, port=port)
        self.sock = self.conn.sock

    def start(self):
        self.conn.start()
