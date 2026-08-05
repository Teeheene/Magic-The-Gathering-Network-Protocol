import socket
import time
from typing import List
from app.server.core.player import Player
from app.server.game.game_state import GameState

class GameSession:
    def __init__(self, max_players=2):
        self.players: List[Player] = []
        self.max_players = max_players
        self.game_state = None
        self.seq_num = 1

    def add_player(self, player: Player):
        self.players.append(player)

    def is_full(self):
        return len(self.players) >= self.max_players

    def start(self):
        print("Starting session with 2 players...")
        player_ids = ["player_1", "player_2"]
        self.game_state = GameState(player_ids)

    def run(self):
        for i, player in enumerate(self.players):
            pid = f"player_{i+1}"
            player.send({"type": "MATCH_START", "player_id": pid, "seq_num": self.seq_num})
            
        self.broadcast_state()

        while True:
            time.sleep(10)
            for player in self.players:
                try:
                    player.send({"type": "HEARTBEAT", "seq_num": self.seq_num})
                except Exception:
                    return

    def broadcast_state(self):
        if not self.game_state:
            return
        self.seq_num += 1
        for i, player in enumerate(self.players):
            pid = f"player_{i+1}"
            pstate = self.game_state.get_personalized_state(pid)
            pdu = {
                "type": "GAME_STATE_UPDATE",
                "seq_num": self.seq_num,
                "state": pstate
            }
            try:
                player.send(pdu)
            except Exception:
                pass



