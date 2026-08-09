from __future__ import annotations

import random
from typing import TYPE_CHECKING
from collections import Counter

if TYPE_CHECKING:
    from app.server.game import Game

ERR_ILLEGAL_DECK = "ILLEGAL_DECK"
ERR_DUPLICATE_ID = "DUPLICATE_ID"
ERR_STALE_ACTION = "STALE_ACTION"
ERR_ILLEGAL_ACTION = "ILLEGAL_ACTION"
ERR_UNKNOWN_TYPE = "UNKNOWN_TYPE"
ERR_INVALID_JSON = "INVALID_JSON"
ERR_INSUFFICIENT_MANA = "INSUFFICIENT_MANA"
ERR_ILLEGAL_TARGET = "ILLEGAL_TARGET"
MSG_DECK_TOO_LARGE = "Deck contains {count} cards; maximum is 50."
MSG_EMPTY_PLAYER_ID = "player_id must be a non-empty string."
MSG_DUPLICATE_ID = "player_id is already claimed by the other player."
MSG_UNKNOWN_TYPE = "Unknown PDU type."
MSG_INVALID_JSON = "Received bytes could not be parsed as valid UTF-8 JSON."
MSG_MULLIGAN_STALE = "Mulligan seq_num does not match the latest GAME_STATE_UPDATE."
MSG_MULLIGAN_WRONG_BOTTOM_COUNT = "cards_to_bottom must contain exactly {count} card(s)."
MSG_MULLIGAN_CARD_NOT_IN_HAND = "cards_to_bottom contains a card that is not in the player's current hand."

class PduDispatcher:
    def __init__(self, server: Game):
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

    def _validate_seq_num(self, client, pdu, source):
        if pdu.get("seq_num") == client.seq_num:
            return True
        error = self.build_error(
            f"seq_num does not match the latest {source}.",
            ERR_STALE_ACTION,
            pdu
        )
        client.send(error)
        return False

    def _validate_priority_action(self, client, pdu):
        if getattr(self.server, "priority_holder", None) != client.pid:
            error = self.build_error(
                "Only the current priority holder may perform this action.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        valid = self._validate_seq_num(client, pdu, "PRIORITY_GRANT")
        if not valid and self.server.priority_holder == client.pid:
            self.send_priority_grant(client, client.pid)
        return valid

    def _validate_phase_seq_num(self, client, pdu):
        if pdu.get("seq_num") == getattr(client, "phase_seq_num", None):
            return True
        error = self.build_error(
            "seq_num does not match the latest PHASE_TRANSITION.",
            ERR_STALE_ACTION,
            pdu
        )
        client.send(error)
        return False

    @staticmethod
    def _zone_card_ids(zone):
        return [
            card.get("id") if isinstance(card, dict) else card
            for card in zone
        ]

    def _next_stack_item_id(self):
        next_id = getattr(self.server, "next_stack_item_id", 1)
        self.server.next_stack_item_id = next_id + 1
        return f"stack_{next_id}"

    def _broadcast_game_state(self):
        for viewing_client in self.server.clients:
            self.send_game_state_update(
                viewing_client,
                self.server.state_builder.build_game_state(viewing_client)
            )

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

        if len(deck_list) > 50:
            error = self.build_error(
                MSG_DECK_TOO_LARGE.format(count=len(deck_list)),
                ERR_ILLEGAL_DECK,
                pdu
            )
            client.send(error)
            return False

        if any(
            not self.server.card_catalog.is_valid_instance_id(card_id)
            for card_id in deck_list
        ):
            error = self.build_error(
                "deck_list contains invalid or unauthorized card IDs.",
                ERR_ILLEGAL_DECK,
                pdu
            )
            client.send(error)
            return False

        if isinstance(player_id, str) and any(
            existing_client is not client
            and isinstance(existing_client.pid, str)
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
        if client not in self.server.clients:
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
        if getattr(self.server, "priority_holder", None) != client.pid:
            error = self.build_error(
                "Only the current priority holder may pass priority.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        if pdu.get("seq_num") != client.seq_num:
            error = self.build_error(
                "PRIORITY_PASS seq_num does not match the latest PRIORITY_GRANT.",
                ERR_STALE_ACTION,
                pdu
            )
            client.send(error)
            self.send_priority_grant(client, client.pid)
            return False

        next_client = self.server.other_client(client)
        if next_client is None:
            error = self.build_error(
                "Cannot pass priority without another connected player.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        self.server.consecutive_priority_passes = (
            getattr(self.server, "consecutive_priority_passes", 0) + 1
        )
        if self.server.consecutive_priority_passes >= 2:
            self.server.consecutive_priority_passes = 0
            self.server.priority_holder = None
            if self.server.stack:
                return self.server.resolve_top_stack_item()
            return self.server.advance_phase()

        self.server.priority_holder = next_client.pid
        self._broadcast_game_state()
        self.send_priority_grant(
            next_client,
            self.server.priority_holder
        )
        return True

    def handle_cast_spell(self, client, pdu):
        if not self._validate_priority_action(client, pdu):
            return False

        card_id = pdu.get("card_id")
        targets = pdu.get("targets")
        mana_payment = pdu.get("mana_payment")
        if (
            not isinstance(card_id, str)
            or not isinstance(targets, list)
            or not isinstance(mana_payment, dict)
        ):
            error = self.build_error(
                "CAST_SPELL requires card_id, targets, and mana_payment.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if card_id not in client.hand:
            error = self.build_error(
                "The spell is not in your hand.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if not self.server.targets_are_legal(card_id, targets):
            error = self.build_error(
                "The spell's targets are missing or illegal.",
                ERR_ILLEGAL_TARGET,
                pdu
            )
            client.send(error)
            return False

        expected_payment = self.server.card_mana_cost(card_id)
        declared_payment = self.server.normalize_mana_payment(mana_payment)
        if expected_payment is None or declared_payment != expected_payment:
            error = self.build_error(
                "mana_payment must match the spell's mana cost.",
                ERR_INSUFFICIENT_MANA,
                pdu
            )
            client.send(error)
            return False

        mana_sources = self.server.select_mana_sources(
            client,
            declared_payment,
        )
        if mana_sources is None:
            error = self.build_error(
                "You do not control enough untapped mana sources.",
                ERR_INSUFFICIENT_MANA,
                pdu
            )
            client.send(error)
            return False

        stack_item_id = self._next_stack_item_id()
        stack_item = {
            "stack_item_id": stack_item_id,
            "item_type": "SPELL",
            "source": card_id,
            "controller": client.pid,
            "targets": list(targets),
            "mana_payment": dict(mana_payment)
        }
        self.server.tap_permanents(mana_sources)
        client.hand.remove(card_id)
        self.server.stack.append(stack_item)
        self.server.consecutive_priority_passes = 0

        for viewing_client in self.server.clients:
            self.send_stack_push(
                viewing_client,
                stack_item_id,
                "SPELL",
                card_id,
                client.pid,
                targets
            )
        self._broadcast_game_state()
        self.send_priority_grant(client, client.pid)
        return True

    def handle_activate_ability(self, client, pdu):
        if not self._validate_priority_action(client, pdu):
            return False

        source_id = pdu.get("source_id")
        ability_index = pdu.get("ability_index")
        targets = pdu.get("targets")
        cost_payment = pdu.get("cost_payment")
        if (
            not isinstance(source_id, str)
            or isinstance(ability_index, bool)
            or not isinstance(ability_index, int)
            or ability_index < 0
            or not isinstance(targets, list)
            or not isinstance(cost_payment, dict)
        ):
            error = self.build_error(
                "ACTIVATE_ABILITY contains invalid ability fields.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if source_id not in self._zone_card_ids(client.battlefield):
            error = self.build_error(
                "The ability source is not on your battlefield.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if not self.server.targets_are_legal(source_id, targets):
            error = self.build_error(
                "The ability's targets are missing or illegal.",
                ERR_ILLEGAL_TARGET,
                pdu
            )
            client.send(error)
            return False


        source_permanent = next(
            permanent
            for permanent in client.battlefield
            if self._zone_card_ids([permanent])[0] == source_id
        )
        expected_cost = self.server.ability_cost(source_id)
        declared_tap = cost_payment.get("tap")
        declared_mana = self.server.normalize_mana_payment(
            cost_payment.get("mana")
        )
        if (
            not isinstance(declared_tap, bool)
            or declared_mana is None
            or declared_tap != expected_cost["tap"]
            or declared_mana != expected_cost["mana"]
        ):
            error = self.build_error(
                "cost_payment must match the ability's activation cost.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        if declared_tap and isinstance(source_permanent, dict):
            if source_permanent.get("tapped"):
                error = self.build_error(
                    "The ability source is already tapped.",
                    ERR_ILLEGAL_ACTION,
                    pdu
                )
                client.send(error)
                return False
            card_data = self.server.card_data(source_id) or {}
            if (
                "creature" in card_data.get("card_type", "").casefold()
                and source_permanent.get("summoning_sick")
            ):
                error = self.build_error(
                    "A summoning-sick creature cannot pay a tap cost.",
                    ERR_ILLEGAL_ACTION,
                    pdu
                )
                client.send(error)
                return False

        mana_sources = self.server.select_mana_sources(
            client,
            declared_mana,
            source_permanent if declared_tap else None,
        )
        if mana_sources is None:
            error = self.build_error(
                "You do not control enough untapped mana sources.",
                ERR_INSUFFICIENT_MANA,
                pdu
            )
            client.send(error)
            return False

        self.server.tap_permanents(mana_sources)
        if declared_tap and isinstance(source_permanent, dict):
            source_permanent["tapped"] = True

        stack_item_id = self._next_stack_item_id()
        stack_item = {
            "stack_item_id": stack_item_id,
            "item_type": "ABILITY",
            "source": source_id,
            "controller": client.pid,
            "ability_index": ability_index,
            "targets": list(targets),
            "cost_payment": dict(cost_payment)
        }
        self.server.stack.append(stack_item)
        self.server.consecutive_priority_passes = 0

        for viewing_client in self.server.clients:
            self.send_stack_push(
                viewing_client,
                stack_item_id,
                "ABILITY",
                source_id,
                client.pid,
                targets
            )
        self._broadcast_game_state()
        self.send_priority_grant(client, client.pid)
        return True

    def handle_trigger_order_response(self, client, pdu):
        if not self._validate_seq_num(client, pdu, "TRIGGER_ORDER"):
            return False

        ordered_trigger_ids = pdu.get("ordered_trigger_ids")
        pending_trigger_ids = getattr(client, "pending_trigger_ids", None)
        if not isinstance(ordered_trigger_ids, list) or not all(
            isinstance(trigger_id, str)
            for trigger_id in ordered_trigger_ids
        ):
            error = self.build_error(
                "ordered_trigger_ids must be a list of trigger IDs.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if pending_trigger_ids is None:
            error = self.build_error(
                "No trigger order is pending.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if Counter(ordered_trigger_ids) != Counter(pending_trigger_ids):
            error = self.build_error(
                "The response must order every pending trigger exactly once.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        client.pending_trigger_ids = None
        self.server.ordered_trigger_ids = list(ordered_trigger_ids)
        self._broadcast_game_state()
        return True

    def handle_trigger_choice_response(self, client, pdu):
        if not self._validate_seq_num(client, pdu, "TRIGGER_CHOICE"):
            return False

        pending = getattr(client, "pending_trigger_choice", None)
        trigger_id = pdu.get("trigger_id")
        accept = pdu.get("accept")
        chosen_target = pdu.get("chosen_target")
        if pending is None:
            error = self.build_error(
                "No trigger choice is pending.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if trigger_id != pending["trigger_id"] or not isinstance(accept, bool):
            error = self.build_error(
                "Invalid trigger choice response.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if accept and pending["requires_target"]:
            if chosen_target not in pending["legal_targets"]:
                error = self.build_error(
                    "The chosen target is not legal.",
                    ERR_ILLEGAL_ACTION,
                    pdu
                )
                client.send(error)
                return False

        client.pending_trigger_choice = None
        self.server.last_trigger_choice = {
            "player_id": client.pid,
            "trigger_id": trigger_id,
            "accept": accept,
            "chosen_target": chosen_target
        }
        self._broadcast_game_state()
        return True

    def handle_declare_attackers(self, client, pdu):
        if getattr(self.server, "phase", None) != "DECLARE_ATTACKERS":
            error = self.build_error(
                "It is not declare attackers.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if client.pid != self.server.active_player:
            error = self.build_error(
                "Only the active player attacks.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if not self._validate_phase_seq_num(client, pdu):
            return False

        attackers = pdu.get("attackers")
        if not isinstance(attackers, list) or not all(
            isinstance(attacker, dict)
            and isinstance(attacker.get("creature_id"), str)
            and isinstance(attacker.get("target"), str)
            for attacker in attackers
        ):
            error = self.build_error(
                "Invalid attackers list.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        creature_ids = [attacker["creature_id"] for attacker in attackers]
        if len(creature_ids) != len(set(creature_ids)):
            error = self.build_error(
                "A creature cannot attack twice.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        battlefield_ids = self._zone_card_ids(client.battlefield)
        if any(creature_id not in battlefield_ids for creature_id in creature_ids):
            error = self.build_error(
                "Every attacker must be on your battlefield.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        opponent = self.server.other_client(client)
        if opponent is None or any(
            attacker["target"] != opponent.pid
            for attacker in attackers
        ):
            error = self.build_error(
                "Every attacker must target the opposing player.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        attacking_permanents = []
        for creature_id in creature_ids:
            _, permanent = self.server.find_permanent(creature_id)
            if isinstance(permanent, dict):
                keywords = {
                    str(keyword).casefold().replace("_", " ")
                    for keyword in permanent.get("keywords", [])
                }
                if "defender" in keywords:
                    error = self.build_error(
                        "Creatures with Defender cannot attack.",
                        ERR_ILLEGAL_ACTION,
                        pdu
                    )
                    client.send(error)
                    return False
                if permanent.get("tapped") or (
                    permanent.get("summoning_sick")
                    and "haste" not in keywords
                ):
                    error = self.build_error(
                        "Tapped or summoning-sick creatures cannot attack.",
                        ERR_ILLEGAL_ACTION,
                        pdu
                    )
                    client.send(error)
                    return False
            attacking_permanents.append(permanent)

        self.server.attackers = list(attackers)
        self.server.attackers_declared = True
        for permanent in attacking_permanents:
            if isinstance(permanent, dict):
                keywords = {
                    str(k).casefold().replace("_", " ")
                    for k in permanent.get("keywords", [])
                }
                if "vigilance" not in keywords:
                    permanent["tapped"] = True
        self._broadcast_game_state()
        return self.server.after_attackers_declared()


    def handle_declare_blockers(self, client, pdu):
        if getattr(self.server, "phase", None) != "DECLARE_BLOCKERS":
            error = self.build_error(
                "It is not declare blockers.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if client.pid == self.server.active_player:
            error = self.build_error(
                "The active player cannot block.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if not self._validate_phase_seq_num(client, pdu):
            return False

        blockers = pdu.get("blockers")
        if not isinstance(blockers, list) or not all(
            isinstance(blocker, dict)
            and isinstance(blocker.get("creature_id"), str)
            and isinstance(blocker.get("blocking_id"), str)
            for blocker in blockers
        ):
            error = self.build_error(
                "Invalid blockers list.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        blocker_ids = [blocker["creature_id"] for blocker in blockers]
        attacking_ids = {
            attacker["creature_id"]
            for attacker in getattr(self.server, "attackers", [])
        }
        if len(blocker_ids) != len(set(blocker_ids)):
            error = self.build_error(
                "A creature cannot block twice.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if any(
            blocker_id not in self._zone_card_ids(client.battlefield)
            for blocker_id in blocker_ids
        ):
            error = self.build_error(
                "Every blocker must be on your battlefield.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        for blocker_id in blocker_ids:
            _, permanent = self.server.find_permanent(blocker_id)
            if isinstance(permanent, dict) and permanent.get("tapped"):
                error = self.build_error(
                    "Tapped creatures cannot block.",
                    ERR_ILLEGAL_ACTION,
                    pdu
                )
                client.send(error)
                return False
        for blocker in blockers:
            blocker_id = blocker["creature_id"]
            blocking_id = blocker["blocking_id"]
            _, blocker_perm = self.server.find_permanent(blocker_id)
            _, attacker_perm = self.server.find_permanent(blocking_id)

            blocker_keywords = self.server.permanent_keywords(blocker_perm)
            attacker_keywords = self.server.permanent_keywords(attacker_perm)

            if "flying" in attacker_keywords:
                if "flying" not in blocker_keywords and "reach" not in blocker_keywords:
                    error = self.build_error(
                        "Ground creatures without Flying or Reach cannot block flying creatures.",
                        ERR_ILLEGAL_ACTION,
                        pdu
                    )
                    client.send(error)
                    return False

        if any(
            blocker["blocking_id"] not in attacking_ids
            for blocker in blockers
        ):

            error = self.build_error(
                "A blocker targets a non-attacker.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        self.server.blockers = list(blockers)
        self.server.blockers_declared = True
        self._broadcast_game_state()
        return self.server.after_blockers_declared()

    def handle_assign_damage_order(self, client, pdu):
        if getattr(self.server, "phase", None) != "ASSIGN_DAMAGE_ORDER":
            error = self.build_error(
                "It is not assign damage order.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if client.pid != self.server.active_player:
            error = self.build_error(
                "Only the attacking player assigns damage order.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if not self._validate_phase_seq_num(client, pdu):
            return False

        attacker_id = pdu.get("attacker_id")
        blocker_order = pdu.get("blocker_order")
        if (
            not isinstance(attacker_id, str)
            or not isinstance(blocker_order, list)
            or not all(isinstance(blocker_id, str) for blocker_id in blocker_order)
        ):
            error = self.build_error(
                "Invalid damage order response.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if attacker_id not in getattr(self.server, "pending_damage_orders", set()):
            error = self.build_error(
                "This attacker does not need a damage order.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        expected_blockers = [
            blocker["creature_id"]
            for blocker in getattr(self.server, "blockers", [])
            if blocker["blocking_id"] == attacker_id
        ]
        if Counter(blocker_order) != Counter(expected_blockers):
            error = self.build_error(
                "blocker_order must contain every blocker exactly once.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        if not hasattr(self.server, "damage_orders"):
            self.server.damage_orders = {}
        self.server.damage_orders[attacker_id] = list(blocker_order)
        return self.server.after_damage_order(attacker_id)

    def handle_play_land(self, client, pdu):
        """
        MTGNP Specification Note:
        - Section 5.4 specifies that PLAY_LAND correlates seq_num with PRIORITY_GRANT.
        - Section 7.5 explicitly states: 'Playing a land is a special action... It does not use the stack and does not require priority.'
        Per course instructions, priority_holder is NOT an independent legality requirement for PLAY_LAND.
        Legality requires: active player, PRECOMBAT_MAIN/POSTCOMBAT_MAIN phase, empty stack, land not already played, card in hand, card is a Land.
        """
        if not self._validate_seq_num(client, pdu, "PRIORITY_GRANT"):
            return False
        if client.pid != self.server.active_player:
            error = self.build_error(
                "Only the active player may play a land.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if self.server.phase not in {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"}:
            error = self.build_error(
                "Lands may only be played in a main phase.",
                ERR_WRONG_PHASE,
                pdu
            )
            client.send(error)
            return False
        if self.server.stack:
            error = self.build_error(
                "Lands may only be played when the stack is empty.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        card_id = pdu.get("card_id")
        if not isinstance(card_id, str) or card_id not in client.hand:
            error = self.build_error(
                "The land is not in your hand.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        card_data = self.server.card_data(card_id) or {}
        if "land" not in card_data.get("card_type", "").casefold():
            error = self.build_error(
                "Card played is not a land.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        land_plays = getattr(self.server, "land_played_this_turn", {})
        if land_plays.get(client.pid, False):
            error = self.build_error(
                "You already played a land this turn.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        client.hand.remove(card_id)
        client.battlefield.append({
            "id": card_id,
            "tapped": False
        })
        land_plays[client.pid] = True
        self.server.land_played_this_turn = land_plays
        self.server.consecutive_priority_passes = 0
        self._broadcast_game_state()
        return True


    def handle_discard(self, client, pdu):
        if not self._validate_seq_num(client, pdu, "GAME_STATE_UPDATE"):
            return False

        if (
            self.server.phase != "CLEANUP"
            or client.pid != self.server.active_player
            or len(client.hand) <= 7
        ):
            error = self.build_error(
                "DISCARD is only requested from the active player at cleanup.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        card_ids = pdu.get("card_ids")
        if not isinstance(card_ids, list) or not all(
            isinstance(card_id, str)
            for card_id in card_ids
        ):
            error = self.build_error(
                "card_ids must be a list of card IDs.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        required_discards = len(client.hand) - 7
        if len(card_ids) != required_discards:
            error = self.build_error(
                f"Discard exactly {required_discards} card(s).",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        if Counter(card_ids) - Counter(client.hand):
            error = self.build_error(
                "A discarded card is not in your hand.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        for card_id in card_ids:
            client.hand.remove(card_id)
            client.graveyard.append(card_id)
        self._broadcast_game_state()
        if (
            self.server.phase == "CLEANUP"
            and client.pid == self.server.active_player
            and len(client.hand) <= 7
        ):
            return self.server.finish_cleanup()
        return True

    def handle_concede(self, client, pdu):
        if pdu.get("player_id") != client.pid:
            error = self.build_error(
                "A player may only concede for themselves.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False

        return self.server.end_game(client, "CONCEDE")

    def handle_ping(self, client, pdu):
        timestamp = pdu.get("timestamp")
        if timestamp is not None and not isinstance(timestamp, (int, float)):
            error = self.build_error(
                "PING timestamp must be numeric.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
            client.send(error)
            return False
        self.send_pong(client, pdu)
        return True

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
        pdu = self._send(
            client,
            "PHASE_TRANSITION",
            from_phase=from_phase,
            to_phase=to_phase,
            active_player=active_player,
            turn=turn
        )
        client.phase_seq_num = pdu["seq_num"]
        return pdu

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
        client.pending_trigger_ids = list(trigger_ids)
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
        client.pending_trigger_choice = {
            "trigger_id": trigger_id,
            "requires_target": requires_target,
            "legal_targets": list(legal_targets or [])
        }
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
