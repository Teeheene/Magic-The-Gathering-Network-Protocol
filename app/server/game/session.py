import socket
import time
from app.server.core.player import Player

class GameSession:
    def __init__(self, max_players):
        self.players = []
        self.max_players = max_players

    def add_player(self, player: Player):
        self.players.append(player)

    def is_full(self):
        if(len(self.players) < self.max_players):
            return False
        return True

    def start(self):
        print("Starting session...")

    def run(self):
        for i, player in enumerate(self.players):
            player.send("hello client " + str(i) + " game is starting...")

        while 1:
            for player in self.players:
                player.send("...whats popping")
                time.sleep(2)



