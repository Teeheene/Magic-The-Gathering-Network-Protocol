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


