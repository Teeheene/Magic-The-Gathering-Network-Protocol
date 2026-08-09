from __future__ import annotations

import random
from typing import TYPE_CHECKING
from collections import Counter

if TYPE_CHECKING:
    from app.server.connection import ServerConnection

ERR_ILLEGAL_DECK = "ILLEGAL_DECK"
ERR_DUPLICATE_ID = "DUPLICATE_ID"
ERR_STALE_ACTION = "STALE_ACTION"
ERR_ILLEGAL_ACTION = "ILLEGAL_ACTION"
ERR_UNKNOWN_TYPE = "UNKNOWN_TYPE"
ERR_INVALID_JSON = "INVALID_JSON"
MSG_DECK_TOO_LARGE = "Deck contains {count} cards; maximum is 51."
MSG_EMPTY_PLAYER_ID = "player_id must be a non-empty string."
MSG_DUPLICATE_ID = "player_id is already claimed by the other player."
MSG_UNKNOWN_TYPE = "Unknown PDU type."
MSG_INVALID_JSON = "Received bytes could not be parsed as valid UTF-8 JSON."
MSG_MULLIGAN_STALE = "Mulligan seq_num does not match the latest GAME_STATE_UPDATE."
MSG_MULLIGAN_WRONG_BOTTOM_COUNT = "cards_to_bottom must contain exactly {count} card(s)."
MSG_MULLIGAN_CARD_NOT_IN_HAND = "cards_to_bottom contains a card that is not in the player's current hand."

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
            error = self.build_error(
                MSG_UNKNOWN_TYPE,
                ERR_UNKNOWN_TYPE,
                pdu
            )
            client.send(error)
            return False

        return handler(client, pdu)

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
        deck_list = pdu.get("deck_list")

        if not player_id or player_id == "":
            error = self.build_error(
                MSG_EMPTY_PLAYER_ID,
                ERR_ILLEGAL_ACTION,
                pdu)
            client.send(error)
            return False

        if not isinstance(deck_list, list) or not deck_list:
            error = self.build_error(
                "deck_list must contain at least one card.",
                ERR_ILLEGAL_DECK,
                pdu
            )
            client.send(error)
            return False

        if len(deck_list) > 51:
            error = self.build_error(
                MSG_DECK_TOO_LARGE.format(count=len(deck_list)),
                ERR_ILLEGAL_DECK,
                pdu
            )
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
        client.deck_list = list(deck_list)
        client.seq_num = self.server.seq_num + 1 
        self.server.clients.append(client)

        print(
            f"{client.pid} accepted. "
            f"({len(self.server.clients)}/{self.server.max_clients})"
        )

        return True

    def handle_mulligan_choice(self, client, pdu):
        # ERROR HANDLINGGG
        required_state = (
            "hand",
            "library"
        )
        if any(not hasattr(client, field) for field in required_state):
            error = self.build_error(
                "The mulligan phase has not been initialized.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        if client.mulligan_kept:
            error = self.build_error(
                "This player has already kept a hand.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        if pdu.get("seq_num") != client.seq_num:
            error = self.build_error(
                MSG_MULLIGAN_STALE,
                ERR_STALE_ACTION,
                pdu
            )
            client.send(error)
            return False
        # ENDS HERE

        keep = pdu.get("keep")
        cards_to_bottom = pdu.get("cards_to_bottom")
        if not isinstance(keep, bool) or not isinstance(cards_to_bottom, list):
            error = self.build_error(
                "MULLIGAN_CHOICE requires a boolean keep and a cards_to_bottom list.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        if not all(isinstance(card_id, str) for card_id in cards_to_bottom):
            error = self.build_error(
                "cards_to_bottom must contain card IDs.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        if not keep:
            if cards_to_bottom:
                error = self.build_error(
                    "Only bottom cards when keeping a hand.",
                    ERR_ILLEGAL_ACTION,
                    pdu
                )
                client.send(error)
                return False

            deck = list(client.library) + list(client.hand)
            random.shuffle(deck)
            client.hand = deck[:7]
            client.library = deck[7:]
            client.mulligan_taken += 1
            self.send_game_state_update(
                client,
                self.server.state_builder.build_mulligan_state(client)
            )
            return True

        if len(cards_to_bottom) != client.mulligan_taken:
            error = self.build_error(
                MSG_MULLIGAN_WRONG_BOTTOM_COUNT.format(
                    count=client.mulligan_taken
                ),
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        if Counter(cards_to_bottom) - Counter(client.hand):
            error = self.build_error(
                MSG_MULLIGAN_CARD_NOT_IN_HAND,
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        for card_id in cards_to_bottom:
            client.hand.remove(card_id)
            client.library.append(card_id)

        client.mulligan_kept = True
        self.send_game_state_update(
            client,
            self.server.state_builder.build_mulligan_state(client)
        )
        return True

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
        return self._send(client, "GAME_STATE_UPDATE", state=state)

    def send_phase_transition(
        self,
        client,
        from_phase,
        to_phase,
        active_player,
        turn
    ):
        return self._send(
            client,
            "PHASE_TRANSITION",
            from_phase=from_phase,
            to_phase=to_phase,
            active_player=active_player,
            turn=turn
        )

    def send_priority_grant(self, client, player_id, time_limit_ms=60000):
        return self._send(
            client,
            "PRIORITY_GRANT",
            player_id=player_id,
            time_limit_ms=time_limit_ms
        )

    def send_stack_push(
        self,
        client,
        stack_item_id,
        item_type,
        source,
        controller,
        targets=None
    ):
        return self._send(
            client,
            "STACK_PUSH",
            stack_item_id=stack_item_id,
            item_type=item_type,
            source=source,
            targets=list(targets or []),
            controller=controller
        )

    def send_trigger_order(self, client, player_id, trigger_ids):
        return self._send(
            client,
            "TRIGGER_ORDER",
            player_id=player_id,
            trigger_ids=list(trigger_ids)
        )

    def send_trigger_choice(
        self,
        client,
        trigger_id,
        source_id,
        effect_summary,
        requires_target=False,
        legal_targets=None
    ):
        return self._send(
            client,
            "TRIGGER_CHOICE",
            trigger_id=trigger_id,
            source_id=source_id,
            effect_summary=effect_summary,
            requires_target=requires_target,
            legal_targets=list(legal_targets or [])
        )

    def send_stack_resolve(
        self,
        client,
        stack_item_id,
        result,
        state_changes=None
    ):
        return self._send(
            client,
            "STACK_RESOLVE",
            stack_item_id=stack_item_id,
            result=result,
            state_changes=list(state_changes or [])
        )

    def send_combat_damage_result(
        self,
        client,
        damage_events,
        life_totals,
        creatures_died=None,
        game_over_result=None
    ):
        payload = {
            "damage_events": list(damage_events),
            "life_totals": dict(life_totals),
            "creatures_died": list(creatures_died or [])
        }
        if game_over_result is not None:
            payload["game_over_result"] = game_over_result
        return self._send(client, "COMBAT_DAMAGE_RESULT", **payload)

    def send_game_over(self, client, winner_id, loser_id, reason):
        return self._send(
            client,
            "GAME_OVER",
            winner_id=winner_id,
            loser_id=loser_id,
            reason=reason
        )

    def send_error(self, client, code, message, rejected_action):
        rejected_seq_num = rejected_action.get("seq_num")
        seq_num = (
            rejected_seq_num
            if isinstance(rejected_seq_num, int)
            else self._next_seq_num()
        )
        return self._send(
            client,
            "ERROR",
            seq_num=seq_num,
            update_client_seq=False,
            code=code,
            message=message,
            rejected_action=rejected_action
        )

    def send_pong(self, client, ping):
        return self._send(
            client,
            "PONG",
            seq_num=ping.get("seq_num", 0),
            update_client_seq=False,
            timestamp=ping.get("timestamp")
        )

    def _next_seq_num(self):
        self.server.seq_num += 1
        return self.server.seq_num

    def _send(
        self,
        client,
        pdu_type,
        seq_num=None,
        update_client_seq=True,
        **payload
    ):
        if seq_num is None:
            seq_num = self._next_seq_num()

        pdu = {
            "type": pdu_type,
            "seq_num": seq_num,
            **payload
        }
        client.send(pdu)

        if update_client_seq:
            client.seq_num = seq_num

        return pdu
