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
ERR_NOT_YOUR_PRIORITY = "NOT_YOUR_PRIORITY"
ERR_WRONG_PHASE = "WRONG_PHASE"
ERR_UNKNOWN_TYPE = "UNKNOWN_TYPE"
ERR_INVALID_JSON = "INVALID_JSON"
ERR_INSUFFICIENT_MANA = "INSUFFICIENT_MANA"
ERR_ILLEGAL_TARGET = "ILLEGAL_TARGET"
ERR_TRIGGER_ORDER_INVALID = "TRIGGER_ORDER_INVALID"
ERR_TRIGGER_CHOICE_INVALID = "TRIGGER_CHOICE_INVALID"
ERR_CARD_CHOICE_INVALID = "CARD_CHOICE_INVALID"

CARD_CHOICE_TYPES = {
    "SELECT_CARDS", "ORDER_CARDS", "YES_NO", "COLOR", "PAY_MANA", "MADNESS_CAST",
}

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
            "CARD_CHOICE_RESPONSE": self.handle_card_choice_response,
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

        if self.server.has_pending_card_choice() and pdu_type not in {
            "CARD_CHOICE_RESPONSE", "PING", "CONCEDE",
        }:
            return self.send_error(
                client, "A mandatory card choice is pending.", ERR_ILLEGAL_ACTION, pdu
            )

        handler = self.handlers.get(pdu_type)
        if handler is None:
            return self.send_error(
                client,
                MSG_UNKNOWN_TYPE,
                ERR_UNKNOWN_TYPE,
                pdu
            )

        return handler(client, pdu)

    def handle_card_choice_response(self, client, pdu):
        pending = getattr(client, "pending_card_choice", None)
        expected = getattr(client, "active_card_choice_seq_num", None)
        if pending is None:
            return self.send_error(client, "No card choice is pending for this player.", ERR_CARD_CHOICE_INVALID, pdu)
        if pdu.get("player_id") != client.pid:
            return self.send_error(client, "player_id does not match the deciding player.", ERR_CARD_CHOICE_INVALID, pdu)
        if pdu.get("seq_num") != expected:
            return self.send_error(client, "seq_num does not match the active card-choice token.", ERR_STALE_ACTION, pdu)
        validator = pending.get("validator")
        normalized = validator(pdu) if callable(validator) else None
        if normalized is None:
            return self.send_error(client, "Invalid card choice response.", ERR_CARD_CHOICE_INVALID, pdu)
        continuation = pending.get("continuation")
        client.pending_card_choice = None
        client.active_card_choice_seq_num = None
        if callable(continuation):
            return continuation(normalized)
        return True

    def build_error(self, message: str, code: str, pdu):
        seq_num = pdu.get("seq_num") if isinstance(pdu, dict) and isinstance(pdu.get("seq_num"), int) else getattr(self.server, "seq_num", 0)
        return {
            "type": "ERROR",
            "seq_num": seq_num,
            "code": code,
            "message": message,
            "rejected_action": pdu if isinstance(pdu, dict) else {}
        }

    def _validate_seq_num(self, client, pdu, source):
        if pdu.get("seq_num") == client.seq_num:
            return True
        return self.send_error(
            client,
            f"seq_num does not match the latest {source}.",
            ERR_STALE_ACTION,
            pdu
        )

    def _validate_priority_action(self, client, pdu):
        if getattr(self.server, "priority_holder", None) != client.pid:
            return self.send_error(
                client,
                "Only the current priority holder may perform this action.",
                ERR_NOT_YOUR_PRIORITY,
                pdu
            )
        expected_seq = getattr(client, "active_priority_seq_num", None)
        if pdu.get("seq_num") != expected_seq:
            self.send_error(
                client,
                "seq_num does not match the active PRIORITY_GRANT token.",
                ERR_STALE_ACTION,
                pdu
            )
            if self.server.priority_holder == client.pid:
                self.reissue_priority_grant(client)
            return False
        return True

    def _validate_land_action(self, client, pdu):
        expected_seq = getattr(client, "active_priority_seq_num", None)
        if expected_seq is not None and pdu.get("seq_num") != expected_seq:
            return self.send_error(
                client,
                "seq_num does not match the active PRIORITY_GRANT token.",
                ERR_STALE_ACTION,
                pdu
            )
        return True

    def reissue_priority_grant(self, client):
        pdu = {
            "type": "PRIORITY_GRANT",
            "seq_num": getattr(client, "active_priority_seq_num", getattr(self.server, "seq_num", 0)),
            "player_id": client.pid,
            "time_limit_ms": 30000
        }
        client.send(pdu)

    def _validate_phase_seq_num(self, client, pdu):
        expected_seq = getattr(client, "active_phase_seq_num", None)
        if pdu.get("seq_num") == expected_seq:
            return True
        return self.send_error(
            client,
            "seq_num does not match the active PHASE_TRANSITION token.",
            ERR_STALE_ACTION,
            pdu
        )

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
            return self.send_error(
                client,
                MSG_EMPTY_PLAYER_ID,
                ERR_ILLEGAL_ACTION,
                pdu
            )

        if not isinstance(deck_list, list) or not deck_list:
            return self.send_error(
                client,
                "deck_list must contain at least one card.",
                ERR_ILLEGAL_DECK,
                pdu
            )

        if len(deck_list) > 50:
            return self.send_error(
                client,
                MSG_DECK_TOO_LARGE.format(count=len(deck_list)),
                ERR_ILLEGAL_DECK,
                pdu
            )

        if not self.server.card_catalog.is_valid_deck(deck_list):
            return self.send_error(
                client,
                "deck_list contains invalid card IDs or duplicate physical instances.",
                ERR_ILLEGAL_DECK,
                pdu
            )

        if isinstance(player_id, str) and any(
            other.pid == player_id and other is not client
            for other in self.server.clients
        ):
            return self.send_error(
                client,
                MSG_DUPLICATE_ID,
                ERR_DUPLICATE_ID,
                pdu
            )

        client.pid = player_id 
        client.deck_list = list(deck_list)
        client.deck = list(deck_list)
        client.ready_in_lobby = True
        client.seq_num = self.server.seq_num + 1 
        if client not in self.server.clients:
            self.server.clients.append(client)

        print(
            f"{client.pid} accepted. "
            f"({len(self.server.clients)}/{self.server.max_clients})"
        )

        return True


    def handle_mulligan_choice(self, client, pdu):
        if self.server.phase != "MULLIGAN":
            return self.send_error(
                client,
                "The mulligan phase has not been initialized.",
                ERR_ILLEGAL_ACTION,
                pdu
            )

        if client.mulligan_kept:
            return self.send_error(
                client,
                "This player has already kept a hand.",
                ERR_ILLEGAL_ACTION,
                pdu
            )

        expected_seq = getattr(client, "active_mulligan_seq_num", None)
        if expected_seq is not None and pdu.get("seq_num") != expected_seq:
            return self.send_error(
                client,
                MSG_MULLIGAN_STALE,
                ERR_STALE_ACTION,
                pdu
            )


        keep = pdu.get("keep")
        cards_to_bottom = pdu.get("cards_to_bottom")
        if not isinstance(keep, bool) or not isinstance(cards_to_bottom, list):
            return self.send_error(
                client,
                "MULLIGAN_CHOICE requires a boolean keep and a cards_to_bottom list.",
                ERR_ILLEGAL_ACTION,
                pdu
            )

        if not all(isinstance(card_id, str) for card_id in cards_to_bottom):
            return self.send_error(
                client,
                "cards_to_bottom must contain card IDs.",
                ERR_ILLEGAL_ACTION,
                pdu
            )

        if not keep:
            if cards_to_bottom:
                return self.send_error(
                    client,
                    "Only bottom cards when keeping a hand.",
                    ERR_ILLEGAL_ACTION,
                    pdu
                )

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
            return self.send_error(
                client,
                MSG_MULLIGAN_WRONG_BOTTOM_COUNT.format(
                    count=client.mulligan_taken
                ),
                ERR_ILLEGAL_ACTION,
                pdu
            )

        if Counter(cards_to_bottom) - Counter(client.hand):
            return self.send_error(
                client,
                MSG_MULLIGAN_CARD_NOT_IN_HAND,
                ERR_ILLEGAL_ACTION,
                pdu
            )

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
        if not self._validate_priority_action(client, pdu):
            return False

        return self.server.register_priority_pass(client)


    def handle_cast_spell(self, client, pdu):
        card_id = pdu.get("card_id")
        targets = pdu.get("targets")
        mana_payment = pdu.get("mana_payment")
        mode = pdu.get("mode")

        if (
            not isinstance(card_id, str)
            or not isinstance(targets, list)
            or not isinstance(mana_payment, dict)
        ):
            return self.send_error(client, "CAST_SPELL requires card_id, targets, and mana_payment.", ERR_ILLEGAL_ACTION, pdu)

        if card_id not in client.hand:
            return self.send_error(client, "The spell is not in your hand.", ERR_ILLEGAL_ACTION, pdu)

        card_data = self.server.card_data(card_id)
        if card_data is None:
            return self.send_error(client, f"Unknown card_id: {card_id}", ERR_ILLEGAL_ACTION, pdu)

        card_type = card_data.get("card_type", "").casefold()
        base_id = self.server.base_card_id(card_id)
        if base_id == "healing_salve":
            if mode not in {"GAIN_LIFE", "PREVENT_DAMAGE"}:
                return self.send_error(client, "Healing Salve requires a valid mode.", ERR_ILLEGAL_ACTION, pdu)
        elif mode is not None:
            return self.send_error(client, "This spell does not accept a mode.", ERR_ILLEGAL_ACTION, pdu)

        # Reject Land via CAST_SPELL
        if "land" in card_type:
            return self.send_error(client, "Lands cannot be cast as spells. Use PLAY_LAND.", ERR_ILLEGAL_ACTION, pdu)

        # Sorcery-speed timing check for Creature, Sorcery, Artifact, Enchantment
        keywords = [k.casefold() for k in card_data.get("keywords", [])]
        is_instant_or_flash = "instant" in card_type or "flash" in keywords

        if not is_instant_or_flash:
            if client.pid != self.server.active_player:
                return self.send_error(client, "Sorcery-speed spells may only be cast on your turn.", ERR_WRONG_PHASE, pdu)
            if self.server.phase not in {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"}:
                return self.send_error(client, "Sorcery-speed spells may only be cast in a main phase.", ERR_WRONG_PHASE, pdu)
            if getattr(self.server, "stack", []):
                return self.send_error(client, "Sorcery-speed spells may only be cast when the stack is empty.", ERR_ILLEGAL_ACTION, pdu)

        if not self._validate_priority_action(client, pdu):
            return False

        if not self.server.targets_are_legal(card_id, targets, controller_id=client.pid, mode=mode):
            return self.send_error(client, "The spell's targets are missing or illegal.", ERR_ILLEGAL_TARGET, pdu)


        expected_payment = self.server.card_mana_cost(card_id)
        declared_payment = self.server.normalize_mana_payment(mana_payment)
        kicker_payment = {
            "goblin_bushwhacker": {"R": 2, "X": 1},
            "vines_of_vastwood": {"G": 2},
        }.get(base_id)
        legal_payments = [expected_payment]
        if kicker_payment is not None:
            legal_payments.append(kicker_payment)
        if expected_payment is None or declared_payment not in legal_payments:
            return self.send_error(
                client,
                "mana_payment must match the spell's mana cost.",
                ERR_INSUFFICIENT_MANA,
                pdu
            )

        mana_payment_plan = self.server.plan_mana_payment(
            client,
            declared_payment,
        )
        if mana_payment_plan is None:
            return self.send_error(
                client,
                "You do not control enough untapped mana sources.",
                ERR_INSUFFICIENT_MANA,
                pdu
            )

        stack_item_id = self._next_stack_item_id()
        stack_item = {
            "stack_item_id": stack_item_id,
            "item_type": "SPELL",
            "source": card_id,
            "controller": client.pid,
            "targets": list(targets),
            "mana_payment": dict(mana_payment),
            "kicked": kicker_payment is not None and declared_payment == kicker_payment,
            "mode": mode,
        }
        self.server.commit_mana_payment(client, mana_payment_plan)
        client.hand.remove(card_id)
        self.server.stack.append(stack_item)
        self.server.consecutive_priority_passes = 0

        # Broadcast spell STACK_PUSH FIRST
        for viewing_client in self.server.clients:
            self.send_stack_push(
                viewing_client,
                stack_item_id,
                "SPELL",
                card_id,
                client.pid,
                targets
            )

        # Publish events and run trigger / SBA / priority pipeline
        from app.server.engine.triggers import GameEvent
        events = [GameEvent("spell_cast", {"card_id": card_id, "controller": client.pid, "targets": targets})]
        for target in targets:
            events.append(GameEvent("became_target", {"target": target, "target_id": target, "source": card_id, "controller": client.pid}))

        self.server.post_event(events)
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
            return self.send_error(
                client,
                "ACTIVATE_ABILITY contains invalid ability fields.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
        if source_id not in self._zone_card_ids(client.battlefield):
            return self.send_error(
                client,
                "The ability source is not on your battlefield.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
        if not self.server.targets_are_legal(
            source_id, targets, is_ability=True, controller_id=client.pid
        ):
            return self.send_error(
                client,
                "The ability's targets are missing or illegal.",
                ERR_ILLEGAL_TARGET,
                pdu
            )


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
            return self.send_error(
                client,
                "cost_payment must match the ability's activation cost.",
                ERR_ILLEGAL_ACTION,
                pdu
            )

        if declared_tap and isinstance(source_permanent, dict):
            if source_permanent.get("tapped"):
                return self.send_error(
                    client,
                    "The ability source is already tapped.",
                    ERR_ILLEGAL_ACTION,
                    pdu
                )
            card_data = self.server.card_data(source_id) or {}
            if (
                "creature" in card_data.get("card_type", "").casefold()
                and source_permanent.get("summoning_sick")
            ):
                return self.send_error(
                    client,
                    "A summoning-sick creature cannot pay a tap cost.",
                    ERR_ILLEGAL_ACTION,
                    pdu
                )

        mana_payment_plan = self.server.plan_mana_payment(
            client,
            declared_mana,
            source_permanent if declared_tap else None,
        )
        if mana_payment_plan is None:
            return self.send_error(
                client,
                "You do not control enough untapped mana sources.",
                ERR_INSUFFICIENT_MANA,
                pdu
            )

        self.server.commit_mana_payment(client, mana_payment_plan)
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

        # Broadcast ability STACK_PUSH FIRST
        for viewing_client in self.server.clients:
            self.send_stack_push(
                viewing_client,
                stack_item_id,
                "ABILITY",
                source_id,
                client.pid,
                targets
            )

        # Publish became_target events and run trigger / SBA / priority pipeline
        from app.server.engine.triggers import GameEvent
        events = []
        for target in targets:
            events.append(GameEvent("became_target", {"target": target, "target_id": target, "source": source_id, "controller": client.pid}))

        self.server.post_event(events if events else None)
        return True

    def handle_trigger_order_response(self, client, pdu):
        expected_seq = getattr(client, "active_trigger_seq_num", None)
        if expected_seq is not None and pdu.get("seq_num") != expected_seq:
            return self.send_error(client, "seq_num does not match active trigger token.", ERR_STALE_ACTION, pdu)

        ordered_trigger_ids = pdu.get("ordered_trigger_ids")
        pending_trigger_ids = getattr(client, "pending_trigger_ids", None)
        if not isinstance(ordered_trigger_ids, list) or not all(
            isinstance(trigger_id, str)
            for trigger_id in ordered_trigger_ids
        ):
            return self.send_error(
                client,
                "ordered_trigger_ids must be a list of trigger IDs.",
                ERR_TRIGGER_ORDER_INVALID,
                pdu
            )
        if pending_trigger_ids is None or Counter(ordered_trigger_ids) != Counter(pending_trigger_ids):
            return self.send_error(
                client,
                "The response must order every pending trigger exactly once.",
                ERR_TRIGGER_ORDER_INVALID,
                pdu
            )

        client.pending_trigger_ids = None
        all_pending = list(self.server.trigger_manager.pending_triggers)

        trg_map = {}
        target_batch_id = None
        for tid in ordered_trigger_ids:
            for trg in all_pending:
                if trg.trigger_id == tid:
                    trg_map[tid] = trg
                    if target_batch_id is None:
                        target_batch_id = getattr(trg, "batch_id", None)
                    break

        reordered = [trg_map[tid] for tid in ordered_trigger_ids if tid in trg_map]
        if target_batch_id:
            self.server.trigger_manager.ordered_batches.add((target_batch_id, client.pid))

        new_pending = []
        reordered_inserted = False
        for trg in all_pending:
            if getattr(trg, "batch_id", None) == target_batch_id and trg.controller == client.pid:
                if not reordered_inserted:
                    new_pending.extend(reordered)
                    reordered_inserted = True
            else:
                new_pending.append(trg)

        self.server.trigger_manager.pending_triggers = new_pending
        return self.server.post_event()

    def handle_trigger_choice_response(self, client, pdu):
        expected_seq = getattr(client, "active_trigger_seq_num", None)
        if expected_seq is not None and pdu.get("seq_num") != expected_seq:
            return self.send_error(client, "seq_num does not match active trigger token.", ERR_STALE_ACTION, pdu)

        pending = getattr(client, "pending_trigger_choice", None)
        trigger_id = pdu.get("trigger_id")
        accept = pdu.get("accept")
        chosen_target = pdu.get("chosen_target")
        if pending is None or trigger_id != pending.get("trigger_id") or not isinstance(accept, bool):
            return self.send_error(client, "Invalid trigger choice response.", ERR_TRIGGER_CHOICE_INVALID, pdu)
        if accept and pending.get("requires_target"):
            if chosen_target not in pending.get("legal_targets", []):
                return self.send_error(client, "The chosen target is not legal.", ERR_ILLEGAL_TARGET, pdu)

        client.pending_trigger_choice = None
        pending_trgs = self.server.trigger_manager.pending_triggers
        match_trg = next((t for t in pending_trgs if t.trigger_id == trigger_id), None)
        if match_trg:
            pending_trgs.remove(match_trg)
            if accept:
                stack_item = {
                    "stack_item_id": self._next_stack_item_id(),
                    "item_type": "TRIGGER_ABILITY",
                    "trigger_id": match_trg.trigger_id,
                    "source": match_trg.source_id,
                    "controller": match_trg.controller,
                    "target": chosen_target,
                    "targets": [chosen_target] if chosen_target else [],
                    "effect_summary": match_trg.effect_summary,
                    "effect_fn": match_trg.effect_fn
                }
                self.server.stack.append(stack_item)
                self.broadcast_stack_push(stack_item)

        return self.server.post_event()


    def handle_declare_attackers(self, client, pdu):
        if getattr(self.server, "phase", None) != "DECLARE_ATTACKERS":
            return self.send_error(client, "It is not declare attackers.", ERR_ILLEGAL_ACTION, pdu)
        if client.pid != self.server.active_player:
            return self.send_error(client, "Only the active player attacks.", ERR_ILLEGAL_ACTION, pdu)
        if not self._validate_phase_seq_num(client, pdu):
            return False

        attackers = pdu.get("attackers")
        if not isinstance(attackers, list) or not all(
            isinstance(attacker, dict)
            and isinstance(attacker.get("creature_id"), str)
            and isinstance(attacker.get("target"), str)
            for attacker in attackers
        ):
            return self.send_error(client, "Invalid attackers list.", ERR_ILLEGAL_ACTION, pdu)

        creature_ids = [attacker["creature_id"] for attacker in attackers]
        if len(creature_ids) != len(set(creature_ids)):
            return self.send_error(client, "A creature cannot attack twice.", ERR_ILLEGAL_ACTION, pdu)

        battlefield_ids = self._zone_card_ids(client.battlefield)
        if any(creature_id not in battlefield_ids for creature_id in creature_ids):
            return self.send_error(client, "Every attacker must be on your battlefield.", ERR_ILLEGAL_ACTION, pdu)

        # Enforce that every attacker is a Creature
        for creature_id in creature_ids:
            card_data = self.server.card_data(creature_id) or {}
            if "creature" not in card_data.get("card_type", "").casefold():
                return self.send_error(client, f"{creature_id} is not a Creature and cannot attack.", ERR_ILLEGAL_ACTION, pdu)
            if self.server.is_pacified(creature_id):
                return self.send_error(client, "A creature enchanted by Pacifism cannot attack.", ERR_ILLEGAL_ACTION, pdu)

        opponent = self.server.other_client(client)
        if opponent is None or any(
            attacker["target"] != opponent.pid
            for attacker in attackers
        ):
            return self.send_error(client, "Every attacker must target the opposing player.", ERR_ILLEGAL_ACTION, pdu)

        attacking_permanents = []
        for creature_id in creature_ids:
            _, permanent = self.server.find_permanent(creature_id)
            if isinstance(permanent, dict):
                keywords = self.server.permanent_keywords(permanent)
                if "defender" in keywords:
                    return self.send_error(client, "Creatures with Defender cannot attack.", ERR_ILLEGAL_ACTION, pdu)
                if permanent.get("tapped") or (
                    permanent.get("summoning_sick")
                    and "haste" not in keywords
                ):
                    return self.send_error(client, "Tapped or summoning-sick creatures cannot attack.", ERR_ILLEGAL_ACTION, pdu)
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

        from app.server.engine.triggers import GameEvent
        events = [
            GameEvent("attacker_declared", {
                "attacker_id": att["creature_id"],
                "creature_id": att["creature_id"],
                "target": att["target"],
                "controller": client.pid
            })
            for att in attackers
        ]
        if events:
            self.server.pending_event_continuation = self.server.after_attackers_declared
            return self.server.post_event(events)

        self._broadcast_game_state()
        return self.server.after_attackers_declared()





    def handle_declare_blockers(self, client, pdu):
        if getattr(self.server, "phase", None) != "DECLARE_BLOCKERS":
            return self.send_error(client, "It is not declare blockers.", ERR_ILLEGAL_ACTION, pdu)
        if client.pid == self.server.active_player:
            return self.send_error(client, "The active player cannot block.", ERR_ILLEGAL_ACTION, pdu)
        if not self._validate_phase_seq_num(client, pdu):
            return False

        blockers = pdu.get("blockers")
        if not isinstance(blockers, list) or not all(
            isinstance(blocker, dict)
            and isinstance(blocker.get("creature_id"), str)
            and isinstance(blocker.get("blocking_id"), str)
            for blocker in blockers
        ):
            return self.send_error(client, "Invalid blockers list.", ERR_ILLEGAL_ACTION, pdu)

        blocker_ids = [blocker["creature_id"] for blocker in blockers]
        attacking_ids = {
            attacker["creature_id"]
            for attacker in getattr(self.server, "attackers", [])
        }
        if len(blocker_ids) != len(set(blocker_ids)):
            return self.send_error(client, "A creature cannot block twice.", ERR_ILLEGAL_ACTION, pdu)

        if any(
            blocker_id not in self._zone_card_ids(client.battlefield)
            for blocker_id in blocker_ids
        ):
            return self.send_error(client, "Every blocker must be on your battlefield.", ERR_ILLEGAL_ACTION, pdu)

        for blocker_id in blocker_ids:
            card_data = self.server.card_data(blocker_id) or {}
            if "creature" not in card_data.get("card_type", "").casefold():
                return self.send_error(client, f"{blocker_id} is not a Creature and cannot block.", ERR_ILLEGAL_ACTION, pdu)
            if self.server.is_pacified(blocker_id):
                return self.send_error(client, "A creature enchanted by Pacifism cannot block.", ERR_ILLEGAL_ACTION, pdu)
            _, permanent = self.server.find_permanent(blocker_id)
            if isinstance(permanent, dict) and permanent.get("tapped"):
                return self.send_error(client, "Tapped creatures cannot block.", ERR_ILLEGAL_ACTION, pdu)

        for blocker in blockers:
            blocker_id = blocker["creature_id"]
            blocking_id = blocker["blocking_id"]
            _, blocker_perm = self.server.find_permanent(blocker_id)
            _, attacker_perm = self.server.find_permanent(blocking_id)

            blocker_keywords = self.server.permanent_keywords(blocker_perm)
            attacker_keywords = self.server.permanent_keywords(attacker_perm)

            if "flying" in attacker_keywords:
                if "flying" not in blocker_keywords and "reach" not in blocker_keywords:
                    return self.send_error(client, "Ground creatures without Flying or Reach cannot block flying creatures.", ERR_ILLEGAL_ACTION, pdu)
            if self.server.is_protected_from(attacker_perm, blocker_perm):
                return self.send_error(client, "A creature cannot block a creature protected from its color.", ERR_ILLEGAL_ACTION, pdu)

        if any(
            blocker["blocking_id"] not in attacking_ids
            for blocker in blockers
        ):
            return self.send_error(client, "A blocker targets a non-attacker.", ERR_ILLEGAL_ACTION, pdu)

        self.server.blockers = list(blockers)
        self.server.blockers_declared = True
        self._broadcast_game_state()
        return self.server.after_blockers_declared()

    def handle_assign_damage_order(self, client, pdu):
        if getattr(self.server, "phase", None) != "ASSIGN_DAMAGE_ORDER":
            return self.send_error(client, "It is not assign damage order.", ERR_ILLEGAL_ACTION, pdu)
        if client.pid != self.server.active_player:
            return self.send_error(client, "Only the attacking player assigns damage order.", ERR_ILLEGAL_ACTION, pdu)
        if not self._validate_phase_seq_num(client, pdu):
            return False

        attacker_id = pdu.get("attacker_id")
        blocker_order = pdu.get("blocker_order")
        if (
            not isinstance(attacker_id, str)
            or not isinstance(blocker_order, list)
            or not all(isinstance(blocker_id, str) for blocker_id in blocker_order)
        ):
            return self.send_error(client, "Invalid damage order response.", ERR_ILLEGAL_ACTION, pdu)
        if attacker_id not in getattr(self.server, "pending_damage_orders", set()):
            return self.send_error(client, "This attacker does not need a damage order.", ERR_ILLEGAL_ACTION, pdu)

        expected_blockers = [
            blocker["creature_id"]
            for blocker in getattr(self.server, "blockers", [])
            if blocker["blocking_id"] == attacker_id
        ]
        if Counter(blocker_order) != Counter(expected_blockers):
            return self.send_error(client, "blocker_order must contain every blocker exactly once.", ERR_ILLEGAL_ACTION, pdu)

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
        if not self._validate_land_action(client, pdu):
            return False

        if client.pid != self.server.active_player:
            return self.send_error(
                client,
                "Only the active player may play a land.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
        if self.server.phase not in {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"}:
            return self.send_error(
                client,
                "Lands may only be played in a main phase.",
                ERR_WRONG_PHASE,
                pdu
            )
        if getattr(self.server, "stack", []):
            return self.send_error(
                client,
                "Lands may only be played when the stack is empty.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
        land_played_map = getattr(self.server, "land_played_this_turn", {})
        if land_played_map.get(client.pid, False):
            return self.send_error(
                client,
                "You have already played a land this turn.",
                ERR_ILLEGAL_ACTION,
                pdu
            )

        card_id = pdu.get("card_id")
        if not isinstance(card_id, str) or card_id not in client.hand:
            return self.send_error(client, "The land is not in your hand.", ERR_ILLEGAL_ACTION, pdu)

        card_data = self.server.card_data(card_id) or {}
        if "land" not in card_data.get("card_type", "").casefold():
            return self.send_error(client, "Card played is not a land.", ERR_ILLEGAL_ACTION, pdu)

        client.hand.remove(card_id)
        client.battlefield.append({
            "id": card_id,
            "tapped": False
        })
        land_played_map[client.pid] = True
        self.server.land_played_this_turn = land_played_map
        self.server.consecutive_priority_passes = 0
        self._broadcast_game_state()
        self.server.grant_priority(client.pid)
        return True


    def handle_discard(self, client, pdu):
        expected_seq = getattr(client, "active_cleanup_seq_num", None)
        if expected_seq is not None and pdu.get("seq_num") != expected_seq:
            return self.send_error(
                client,
                "seq_num does not match the active CLEANUP token.",
                ERR_STALE_ACTION,
                pdu
            )

        if (
            self.server.phase != "CLEANUP"
            or client.pid != self.server.active_player
            or len(client.hand) <= 7
        ):
            return self.send_error(
                client,
                "DISCARD is only requested from the active player at cleanup.",
                ERR_ILLEGAL_ACTION,
                pdu
            )

        card_ids = pdu.get("card_ids")
        if not isinstance(card_ids, list) or not all(
            isinstance(card_id, str)
            for card_id in card_ids
        ):
            return self.send_error(
                client,
                "card_ids must be a list of card IDs.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
        required_discards = len(client.hand) - 7
        if len(card_ids) != required_discards:
            return self.send_error(
                client,
                f"Discard exactly {required_discards} card(s).",
                ERR_ILLEGAL_ACTION,
                pdu
            )
        if Counter(card_ids) - Counter(client.hand):
            return self.send_error(
                client,
                "A discarded card is not in your hand.",
                ERR_ILLEGAL_ACTION,
                pdu
            )


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
        player_id = pdu.get("player_id")
        if not player_id or player_id != client.pid:
            return self.send_error(
                client,
                "A player may only concede for themselves.",
                ERR_ILLEGAL_ACTION,
                pdu
            )

        seq_num = pdu.get("seq_num")
        expected_seq = getattr(client, "last_sent_pdu_seq_num", None)
        if expected_seq is None:
            expected_seq = getattr(client, "seq_num", None)
        if seq_num is None or seq_num != expected_seq:
            return self.send_error(
                client,
                "CONCEDE seq_num does not match active sequence token.",
                ERR_STALE_ACTION,
                pdu
            )

        return self.server.end_game(client, "CONCEDE")

    def handle_ping(self, client, pdu):
        timestamp = pdu.get("timestamp")
        if timestamp is not None and not isinstance(timestamp, (int, float)):
            return self.send_error(
                client,
                "PING timestamp must be numeric.",
                ERR_ILLEGAL_ACTION,
                pdu
            )
        self.send_pong(client, pdu)
        return True

    #SEND PDUS
    def send_game_state_update(self, client, state):
        pdu = self._send(client, "GAME_STATE_UPDATE", state=state)
        phase = state.get("phase") if isinstance(state, dict) else None
        if phase == "MULLIGAN":
            client.active_mulligan_seq_num = pdu["seq_num"]
        elif phase == "CLEANUP":
            client.active_cleanup_seq_num = pdu["seq_num"]
        return pdu

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
        client.active_phase_seq_num = pdu["seq_num"]
        return pdu

    def send_priority_grant(self, client, player_id, time_limit_ms=60000):
        pdu = self._send(
            client,
            "PRIORITY_GRANT",
            player_id=player_id,
            time_limit_ms=time_limit_ms
        )
        client.active_priority_seq_num = pdu["seq_num"]
        import time
        client.priority_deadline = time.monotonic() + (time_limit_ms / 1000.0)
        return pdu

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

    def broadcast_stack_push(self, stack_item):
        for client in list(self.server.clients):
            self.send_stack_push(
                client,
                stack_item.get("stack_item_id"),
                stack_item.get("item_type"),
                stack_item.get("source"),
                stack_item.get("controller"),
                stack_item.get("targets")
            )

    def send_trigger_order(self, client, player_id, trigger_ids):
        client.pending_trigger_ids = list(trigger_ids)
        pdu = self._send(
            client,
            "TRIGGER_ORDER",
            player_id=player_id,
            trigger_ids=list(trigger_ids)
        )
        client.active_trigger_seq_num = pdu["seq_num"]
        return pdu

    def send_trigger_order_prompt(self, client, player_id, trigger_ids):
        return self.send_trigger_order(client, player_id, trigger_ids)

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
        pdu = self._send(
            client,
            "TRIGGER_CHOICE",
            trigger_id=trigger_id,
            source_id=source_id,
            effect_summary=effect_summary,
            requires_target=requires_target,
            legal_targets=list(legal_targets or [])
        )
        client.active_trigger_seq_num = pdu["seq_num"]
        return pdu

    def send_trigger_choice_prompt(self, client, trg):
        return self.send_trigger_choice(
            client,
            trg.trigger_id,
            trg.source_id,
            trg.effect_summary,
            requires_target=getattr(trg, "requires_target", False),
            legal_targets=getattr(trg, "legal_targets", [])
        )

    def send_card_choice_request(
        self, client, source_card_id, choice_type, prompt,
        min_choices=0, max_choices=0, options=None,
        validator=None, continuation=None, **details
    ):
        if choice_type not in CARD_CHOICE_TYPES:
            raise ValueError(f"Unsupported card choice type: {choice_type}")
        safe_options = list(options or [])
        client.pending_card_choice = {
            "source_card_id": source_card_id,
            "choice_type": choice_type,
            "min_choices": min_choices,
            "max_choices": max_choices,
            "options": safe_options,
            "validator": validator,
            "continuation": continuation,
        }
        pdu = self._send(
            client, "CARD_CHOICE_REQUEST",
            player_id=client.pid,
            source_card_id=source_card_id,
            choice_type=choice_type,
            prompt=prompt,
            min_choices=min_choices,
            max_choices=max_choices,
            options=safe_options,
            **details,
        )
        client.active_card_choice_seq_num = pdu["seq_num"]
        self.server.priority_holder = None
        return pdu

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

    def broadcast_stack_resolve(self, stack_item_id, result, state_changes=None):
        for client in list(self.server.clients):
            self.send_stack_resolve(client, stack_item_id, result, state_changes)


    def broadcast_combat_damage_result(
        self,
        damage_events,
        life_totals,
        creatures_died=None,
        game_over_result=None
    ):
        for client in list(self.server.clients):
            self.send_combat_damage_result(
                client,
                damage_events,
                life_totals,
                creatures_died,
                game_over_result
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

    def broadcast_game_over(self, winner_id: str, reason: str):
        for client in list(self.server.clients):
            try:
                loser_id = next((c.pid for c in self.server.clients if c.pid != winner_id), None)
                self.send_game_over(client, winner_id=winner_id, loser_id=loser_id, reason=reason)
            except Exception:
                pass


    def send_error(self, client, message: str, code: str, pdu=None):
        rejected_action = pdu if isinstance(pdu, dict) else {}
        rejected_seq_num = rejected_action.get("seq_num")
        seq_num = (
            rejected_seq_num
            if isinstance(rejected_seq_num, int)
            else self._next_seq_num()
        )
        self._send(
            client,
            "ERROR",
            seq_num=seq_num,
            update_client_seq=False,
            code=code,
            message=message,
            rejected_action=rejected_action
        )
        return False


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
        client.last_sent_pdu_seq_num = seq_num

        if update_client_seq:
            client.seq_num = seq_num

        return pdu
