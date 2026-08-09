import random

"""
    functions in this file include the ff:
    build_lobby_state(self)
    build_mulligan_state(self, viewing_client)
    build_untap_state()

    NOTE: These states appear inside of GAME_STATE_UPDATE
"""

class StateBuilder:
    def __init__(self, server):
        self.server = server

    def build_lobby_state(self):
        players_ready = len(self.server.clients)
        waiting_for = [
            f"player_{player_number}"
            for player_number in range(players_ready + 1, self.server.max_clients + 1)
        ]

        return {
            "phase": "LOBBY",
            "players_ready": players_ready,
            "waiting_for": waiting_for
        }

    def build_mulligan_state(
        self,
        viewing_client
    ):
        clients = self.server.clients
        if not clients:
            raise RuntimeError("Cannot build mulligan state without players.")

        #setup
        if not hasattr(self.server, "turn"):
            self.server.turn = 0
        if getattr(self.server, "phase", "LOBBY") == "LOBBY":
            self.server.phase = "MULLIGAN"
        rng = getattr(self.server, "rng", random)
        if getattr(self.server, "active_player", None) not in {
            client.pid for client in clients
        }:
            self.server.active_player = rng.choice(clients).pid
        if not hasattr(self.server, "stack"):
            self.server.stack = []
        for client in clients:
            if not hasattr(client, "hand") or not hasattr(client, "library"):
                deck = list(getattr(client, "deck_list", []))
                if not deck:
                    raise RuntimeError(f"No deck is stored for {client.pid}.")
                rng.shuffle(deck)
                client.hand = deck[:7]
                client.library = deck[7:]
            if not hasattr(client, "life_total"):
                client.life_total = 20
            if not hasattr(client, "battlefield"):
                client.battlefield = []
            if not hasattr(client, "graveyard"):
                client.graveyard = []

        return {
            "turn": self.server.turn,
            "phase": self.server.phase,
            "active_player": self.server.active_player,
            "life_totals": {
                client.pid: client.life_total
                for client in clients
            },
            "hand": {
                viewing_client.pid: list(viewing_client.hand)
            },
            "hand_counts": {
                client.pid: len(client.hand)
                for client in clients
            },
            "library_counts": {
                client.pid: len(client.library)
                for client in clients
            },
            "battlefield": {
                client.pid: list(client.battlefield)
                for client in clients
            },
            "graveyard": {
                client.pid: list(client.graveyard)
                for client in clients
            },
            "stack": list(self.server.stack),
        }

    def build_untap_state(self, viewing_client):
        clients = self.server.clients
        if not clients:
            raise RuntimeError("Cannot build untap state without players.")
        if viewing_client not in clients:
            raise ValueError("viewing_client must be in the current game.")

        self.server.phase = "UNTAP"

        return {
            "turn": self.server.turn,
            "phase": self.server.phase,
            "active_player": self.server.active_player,
            "priority_holder": None,
            "life_totals": {
                client.pid: client.life_total
                for client in clients
            },
            "hand": {
                viewing_client.pid: list(viewing_client.hand)
            },
            "hand_counts": {
                client.pid: len(client.hand)
                for client in clients
            },
            "library_counts": {
                client.pid: len(client.library)
                for client in clients
            },
            "battlefield": {
                client.pid: list(client.battlefield)
                for client in clients
            },
            "graveyard": {
                client.pid: list(client.graveyard)
                for client in clients
            },
            "stack": list(self.server.stack),
        }
