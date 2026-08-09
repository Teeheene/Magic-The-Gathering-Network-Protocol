import random


TURN_PHASES = (
    "UNTAP",
    "UPKEEP",
    "DRAW",
    "PRECOMBAT_MAIN",
    "BEGIN_COMBAT",
    "DECLARE_ATTACKERS",
    "DECLARE_BLOCKERS",
    "ASSIGN_DAMAGE_ORDER",
    "FIRST_STRIKE_DAMAGE",
    "COMBAT_DAMAGE",
    "END_OF_COMBAT",
    "POSTCOMBAT_MAIN",
    "END_STEP",
    "CLEANUP"
)

GAME_PHASES = (
    "LOBBY",
    "GAME_SETUP",
    "MULLIGAN",
    *TURN_PHASES,
    "GAME_OVER",
)

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

    def build_game_state(self, viewing_client):
        clients = self.server.clients
        if viewing_client not in clients:
            raise ValueError("viewing_client must be in the current game.")

        return {
            "turn": self.server.turn,
            "phase": self.server.phase,
            "active_player": self.server.active_player,
            "priority_holder": getattr(self.server, "priority_holder", None),
            "land_played_this_turn": getattr(
                self.server,
                "land_played_this_turn",
                {}
            ).get(self.server.active_player, False),
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
            "stack": list(getattr(self.server, "stack", [])),
            "attackers": list(getattr(self.server, "attackers", [])),
            "blockers": list(getattr(self.server, "blockers", [])),
            "damage_orders": dict(getattr(self.server, "damage_orders", {})),
            "attackers_declared": getattr(
                self.server,
                "attackers_declared",
                False
            ),
            "blockers_declared": getattr(
                self.server,
                "blockers_declared",
                False
            ),
            "pending_damage_orders": list(
                getattr(self.server, "pending_damage_orders", set())
            ),
        }

    def build_phase_state(self, viewing_client, phase):
        if phase not in GAME_PHASES:
            raise ValueError(f"Unknown game phase: {phase}")
        self.server.phase = phase
        return self.build_game_state(viewing_client)

    def build_game_setup_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "GAME_SETUP")

    def build_upkeep_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "UPKEEP")

    def build_draw_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "DRAW")

    def build_precombat_main_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "PRECOMBAT_MAIN")

    def build_begin_combat_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "BEGIN_COMBAT")

    def build_declare_attackers_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "DECLARE_ATTACKERS")

    def build_declare_blockers_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "DECLARE_BLOCKERS")

    def build_assign_damage_order_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "ASSIGN_DAMAGE_ORDER")

    def build_first_strike_damage_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "FIRST_STRIKE_DAMAGE")

    def build_combat_damage_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "COMBAT_DAMAGE")

    def build_end_of_combat_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "END_OF_COMBAT")

    def build_postcombat_main_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "POSTCOMBAT_MAIN")

    def build_end_step_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "END_STEP")

    def build_cleanup_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "CLEANUP")

    def build_game_over_state(self, viewing_client):
        return self.build_phase_state(viewing_client, "GAME_OVER")
