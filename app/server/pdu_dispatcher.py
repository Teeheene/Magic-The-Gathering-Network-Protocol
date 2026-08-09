from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.server.connection import ServerConnection

ERR_ILLEGAL_DECK = "ILLEGAL_DECK"
ERR_DUPLICATE_ID = "DUPLICATE_ID"
ERR_ILLEGAL_ACTION = "ILLEGAL_ACTION"
ERR_UNKNOWN_TYPE = "UNKNOWN_TYPE"
ERR_INVALID_JSON = "INVALID_JSON"
MSG_DECK_TOO_LARGE = "Deck contains {count} cards; maximum is 50."
MSG_EMPTY_PLAYER_ID = "player_id must be a non-empty string."
MSG_DUPLICATE_ID = "player_id is already claimed by the other player."
MSG_UNKNOWN_TYPE = "Unknown PDU type."
MSG_INVALID_JSON = "Received bytes could not be parsed as valid UTF-8 JSON."

class PduDispatcher:
    def __init__(self, server: ServerConnection):
        self.server = server

        self.handlers = {
            "PLAYER_READY": self.handle_player_ready,
            "MULLIGAN_CHOICE": self.handle_mulligan_choice,
            "PRIORITY_PASS": self.handle_priority_pass,
            "CAST_SPELL": self.handle_cast_spell,
            "ACTIVATE_ABILITY": self.handle_activate_ability,
            "TRIGGER_ORDER_RESPONSE": self.handle_trigger_order_response,
            "TRIGGER_CHOICE_RESPONSE": self.handle_trigger_choice_response,
            "DECLARE_ATTACKERS": self.handle_declare_attackers,
            "DECLARE_BLOCKERS": self.handle_declare_blockers,
            "ASSIGN_DAMAGE_ORDER": self.handle_assign_damage_order,
            "PLAY_LAND": self.handle_play_land,
            "DISCARD": self.handle_discard,
            "CONCEDE": self.handle_concede,
            "PING": self.handle_ping,
        }

    def handle(self, client, pdu):
        pdu_type = pdu.get("type")

        handler = self.handlers.get(pdu_type)
        if handler is None:
            raise ValueError(
                f"Unknown PDU type: {pdu_type}"
            )

        handler(client, pdu)

    #errors
    def build_error(self, message: str, code: str, pdu):
        return {
            "type": "ERROR",
            "seq_num": self.server.seq_num,
            "code": code,
            "message": message,
            "rejected_action": pdu 
        }

    #RECEIVE PDUS
    def handle_player_ready(self, client, pdu):
        player_id = pdu.get("player_id")
        if not player_id or player_id == "":
            error = self.build_error(
                ERR_ILLEGAL_ACTION, 
                MSG_EMPTY_PLAYER_ID, 
                pdu)
            client.send(error)
            return False

        if isinstance(player_id, str) and any(
            isinstance(existing_client.pid, str)
            and existing_client.pid.casefold() == player_id.casefold()
            for existing_client in self.server.clients
        ):
            error = self.build_error(
                MSG_DUPLICATE_ID,
                ERR_DUPLICATE_ID,
                pdu
            )
            client.send(error)
            return False

        client.pid = player_id 
        client.seq_num = self.server.seq_num + 1 
        self.server.clients.append(client)

        print(
            f"{client.pid} accepted. "
            f"({len(self.server.clients)}/{self.server.max_clients})"
        )

        return True

    def handle_mulligan_choice(self, client, pdu):
        pass

    def handle_priority_pass(self, client, pdu):
        pass

    def handle_cast_spell(self, client, pdu):
        pass

    def handle_activate_ability(self, client, pdu):
        pass

    def handle_trigger_order_response(self, client, pdu):
        pass

    def handle_trigger_choice_response(self, client, pdu):
        pass

    def handle_declare_attackers(self, client, pdu):
        pass

    def handle_declare_blockers(self, client, pdu):
        pass

    def handle_assign_damage_order(self, client, pdu):
        pass

    def handle_play_land(self, client, pdu):
        pass

    def handle_discard(self, client, pdu):
        pass

    def handle_concede(self, client, pdu):
        pass

    def handle_ping(self, client, pdu):
        pass

    #SEND PDUS
    def send_game_state_update(self, client, state):
        client.send({
            "type": "GAME_STATE_UPDATE",
            "seq_num": client.seq_num + 1,
            "state": state
        })
        pass

    def send_phase_transition(self, client):
        pass

    def send_priority_grant(self, client):
        pass

    def send_stack_push(self, client):
        pass

    def send_trigger_order(self, client):
        pass

    def send_trigger_choice(self, client):
        pass

    def send_stack_resolve(self, client):
        pass

    def send_combat_damage_result(self, client):
        pass

    def send_game_over(self, client):
        pass

    def send_error(self, client):
        pass

    def send_pong(self, client):
        pass
