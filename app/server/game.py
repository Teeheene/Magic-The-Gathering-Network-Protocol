import json
import select
import random
import re
import time
from collections import Counter
from pathlib import Path
from typing import Optional

from app.server.pdu_dispatcher import PduDispatcher
from app.server.game_state import StateBuilder
from app.shared.card_catalog import CardCatalog
from app.server.engine.triggers import EventBus, TriggerManager, GameEvent
from app.server.engine.sba import StateBasedActions
from app.server.engine.effects import CardEffects

CATALOG_PATH = Path(__file__).resolve().parents[1] / "shared" / "card_catalog.json"



class Game:
    def __init__(self, connection):
        self.connection = connection
        self.clients = connection.clients
        self.max_clients = connection.max_clients
        self.card_catalog = CardCatalog(CATALOG_PATH)
        self.seq_num = 0
        self.pdu_dispatcher = PduDispatcher(self)
        self.state_builder = StateBuilder(self)
        self.reset()

    def reset(self):
        self.phase = "LOBBY"
        self.turn = 0
        self.active_player = None
        self.priority_holder = None
        self.stack = []
        self.land_played_this_turn = {}
        self.consecutive_priority_passes = 0
        self.attackers = []
        self.blockers = []
        self.damage_orders = {}
        self.pending_damage_orders = set()
        self.attackers_declared = False
        self.blockers_declared = False
        self.pending_event_continuation = None
        self.next_stack_item_id = 1
        self.event_bus = EventBus()
        self.trigger_manager = TriggerManager(self, self.card_catalog)
        self.cant_gain_life_this_turn = False
        self.cant_prevent_damage_this_turn = False
        self.suspended_cards = []
        for client in getattr(self, "clients", []):
            client.ready_in_lobby = False



    def game_setup(self):
        """Initialize a fresh match before players begin mulligans."""
        self.turn = 0
        self.priority_holder = None
        self.stack = []
        self.land_played_this_turn = {
            client.pid: False
            for client in self.clients
        }
        self.consecutive_priority_passes = 0
        self.attackers = []
        self.blockers = []
        self.damage_orders = {}
        self.pending_damage_orders = set()
        self.attackers_declared = False
        self.blockers_declared = False
        self.next_stack_item_id = 1
        self.suspended_cards = []
        self.game_over = False

        rng = getattr(self, "rng", random)
        self.active_player = rng.choice(self.clients).pid
        for client in self.clients:
            deck_cards = getattr(client, "deck_list", getattr(client, "deck", []))
            deck = list(deck_cards)
            rng.shuffle(deck)
            client.hand = deck[:7]
            client.library = deck[7:]
            client.life_total = 20
            client.battlefield = []
            client.graveyard = []
            client.exile = []
            client.mulligan_taken = 0
            client.mulligan_kept = False
            client.pending_card_choice = None
            client.active_card_choice_seq_num = None

        if not self.transition_phase("GAME_SETUP"):
            return False
        return self.broadcast_game_state()

    def return_to_lobby(self, disconnected_client):
        return self.connection.return_to_lobby(disconnected_client)

    def client_for_player(self, player_id):
        return next(
            (
                client
                for client in self.clients
                if client.pid == player_id
            ),
            None
        )

    def other_client(self, client):
        return next(
            (
                other_client
                for other_client in self.clients
                if other_client is not client
            ),
            None
        )

    def card_data(self, card_id):
        data = self.card_catalog.get_card_data(card_id)
        if data is not None:
            return data
        base_id = re.sub(r"_\d+$", "", card_id)
        return self.card_catalog.get_card_data(base_id)

    @staticmethod
    def base_card_id(card_id):
        return re.sub(r"_\d+$", "", card_id)

    def target_exists(self, target_id):
        if self.client_for_player(target_id) is not None:
            return True
        if self.find_permanent(target_id)[1] is not None:
            return True
        return any(
            item.get("stack_item_id") == target_id
            for item in self.stack
        )

    def targets_are_legal(self, card_id, targets, is_ability=False, controller_id=None, mode=None):
        card_data = self.card_data(card_id) or {}
        source_color = {
            "W": "white", "U": "blue", "B": "black", "R": "red", "G": "green",
        }.get(str(card_data.get("color", "")).upper(), "")
        card_type = card_data.get("card_type", "").casefold()
        text = card_data.get("text", "").casefold()

        base_id = self.base_card_id(card_id)

        # Non-Aura permanents do not target on cast.
        if (
            not is_ability
            and base_id != "pacifism"
            and ("creature" in card_type or "artifact" in card_type or "enchantment" in card_type or "land" in card_type)
        ):
            return not targets

        requires_target = "target" in text or base_id == "pacifism"
        if not requires_target:
            return not targets
        if len(targets) != 1:
            return False

        target_id = targets[0]
        if base_id == "healing_salve":
            if mode == "GAIN_LIFE":
                return self.client_for_player(target_id) is not None
            if mode == "PREVENT_DAMAGE":
                return self.target_exists(target_id)
            return False
        if base_id == "raise_dead":
            controller = self.client_for_player(controller_id)
            if controller is None or target_id not in controller.graveyard:
                return False
            target_data = self.card_data(target_id) or {}
            return "creature" in target_data.get("card_type", "").casefold()

        target_owner, target_permanent = self.find_permanent(target_id)
        if isinstance(target_permanent, dict):
            target_data = self.card_data(target_permanent.get("id", "")) or {}
            target_keywords = self.permanent_keywords(target_permanent)
            target_keywords.update(
                str(keyword).casefold().replace("_", " ")
                for keyword in target_data.get("keywords", [])
            )
            if (
                "hexproof" in target_keywords
                and target_owner is not None
                and target_owner.pid != controller_id
            ):
                return False
            if base_id == "mother_of_runes" and (
                target_owner is None or target_owner.pid != controller_id
            ):
                return False
            if f"protection from {source_color}" in target_keywords:
                return False
            if (
                target_owner is not None
                and target_owner.pid != controller_id
                and target_permanent.get("opponent_targeting_blocked_until_eot")
            ):
                return False

        # Counterspells: target must be on stack
        if base_id in {"counterspell", "cancel", "mana_leak", "negate"}:
            stack_item = next(
                (item for item in self.stack if item.get("stack_item_id") == target_id),
                None,
            )
            if stack_item is None:
                return False
            if base_id == "negate":
                target_source_id = stack_item.get("source", "")
                target_card_data = self.card_data(target_source_id) or {}
                if "creature" in target_card_data.get("card_type", "").casefold():
                    return False
            return True

        # Player-only targets
        if base_id in {"lava_spike", "millstone"} or "target player" in text:
            return self.client_for_player(target_id) is not None

        # Creature-only targets
        if base_id in {
            "flame_slash", "unsummon", "royal_assassin", "terror", "doom_blade"
        } or "target creature" in text:
            owner, permanent = self.find_permanent(target_id)
            if permanent is None or not isinstance(permanent, dict):
                return False
            perm_data = self.card_data(permanent.get("id", "")) or {}
            if "creature" not in perm_data.get("card_type", "").casefold() and permanent.get("toughness") is None:
                return False
            if base_id == "royal_assassin":
                if not permanent.get("tapped"):
                    return False
            if base_id == "terror":
                if "artifact" in perm_data.get("card_type", "").casefold() or perm_data.get("color") == "B":
                    return False
            if base_id == "doom_blade":
                if perm_data.get("color") == "B":
                    return False
            return True

        # Artifact / Enchantment targets
        if base_id == "naturalize":
            owner, permanent = self.find_permanent(target_id)
            if permanent is None or not isinstance(permanent, dict):
                return False
            perm_data = self.card_data(permanent.get("id", "")) or {}
            perm_type = perm_data.get("card_type", "").casefold()
            return "artifact" in perm_type or "enchantment" in perm_type

        return self.target_exists(target_id)



    @staticmethod
    def normalize_mana_payment(payment):
        if not isinstance(payment, dict):
            return None
        normalized = {}
        for color, amount in payment.items():
            key = "X" if color == "Generic" else color
            if (
                key not in {"W", "U", "B", "R", "G", "C", "X"}
                or isinstance(amount, bool)
                or not isinstance(amount, int)
                or amount < 0
            ):
                return None
            if amount:
                normalized[key] = normalized.get(key, 0) + amount
        return normalized

    def card_mana_cost(self, card_id):
        card_data = self.card_data(card_id)
        if card_data is None:
            return None
        return self.normalize_mana_payment(card_data.get("mana_cost", {}))

    def register_priority_pass(self, client):
        next_client = self.other_client(client)
        if next_client is None:
            return self.pdu_dispatcher.send_error(
                client,
                "Cannot pass priority without another connected player.",
                "ILLEGAL_ACTION"
            )

        self.consecutive_priority_passes = (
            getattr(self, "consecutive_priority_passes", 0) + 1
        )
        if self.consecutive_priority_passes >= 2:
            self.consecutive_priority_passes = 0
            self.priority_holder = None
            if self.stack:
                return self.resolve_top_stack_item()
            return self.advance_phase()

        self.priority_holder = next_client.pid
        self.pdu_dispatcher._broadcast_game_state()
        self.pdu_dispatcher.send_priority_grant(
            next_client,
            self.priority_holder
        )
        return True

    def ability_cost(self, source_id):
        card_data = self.card_data(source_id) or {}
        text = card_data.get("text", "")
        cost_text = text.split(":", 1)[0] if ":" in text else ""
        mana = Counter()
        for symbol in re.findall(r"\{([^}]+)\}", cost_text):
            if symbol.isdigit():
                mana["X"] += int(symbol)
            elif symbol in {"W", "U", "B", "R", "G", "C"}:
                mana[symbol] += 1
        return {
            "tap": "tap" in cost_text.casefold(),
            "mana": dict(mana),
        }

    def permanent_mana(self, permanent):
        if not isinstance(permanent, dict) or permanent.get("tapped"):
            return []
        card_data = self.card_data(permanent.get("id", "")) or {}
        card_type = card_data.get("card_type", "").casefold()
        if "creature" in card_type and permanent.get("summoning_sick"):
            return []
        text = card_data.get("text", "")
        if ":" not in text:
            return []
        effect = text.split(":", 1)[1].strip()
        if not effect.casefold().startswith("add "):
            return []
        return [
            symbol
            for symbol in re.findall(r"\{([^}]+)\}", effect)
            if symbol in {"W", "U", "B", "R", "G", "C"}
        ]

    def select_mana_sources(self, client, payment, excluded_permanent=None):
        required = self.normalize_mana_payment(payment)
        if required is None:
            return None

        candidates = [
            (permanent, self.permanent_mana(permanent))
            for permanent in client.battlefield
            if permanent is not excluded_permanent
        ]
        candidates = [candidate for candidate in candidates if candidate[1]]
        selected = []
        pool = Counter()

        for color in ("W", "U", "B", "R", "G", "C"):
            while pool[color] < required.get(color, 0):
                candidate_index = next(
                    (
                        index
                        for index, (_, produced) in enumerate(candidates)
                        if color in produced
                    ),
                    None,
                )
                if candidate_index is None:
                    return None
                permanent, produced = candidates.pop(candidate_index)
                selected.append(permanent)
                pool.update(produced)

        remaining_pool = sum(
            pool[color] - required.get(color, 0)
            for color in ("W", "U", "B", "R", "G", "C")
        )
        generic_required = required.get("X", 0)
        while remaining_pool < generic_required:
            if not candidates:
                return None
            permanent, produced = candidates.pop(0)
            selected.append(permanent)
            remaining_pool += len(produced)

        return selected

    def plan_mana_payment(self, client, payment, excluded_permanent=None):
        required = self.normalize_mana_payment(payment)
        if required is None:
            return None

        available_pool = Counter(getattr(client, "mana_pool", {}) or {})
        spent_pool = Counter()
        remaining = Counter(required)
        for color in ("W", "U", "B", "R", "G", "C"):
            amount = min(available_pool[color], remaining[color])
            spent_pool[color] += amount
            available_pool[color] -= amount
            remaining[color] -= amount

        generic_needed = remaining["X"]
        for color in ("C", "W", "U", "B", "R", "G"):
            amount = min(available_pool[color], generic_needed)
            spent_pool[color] += amount
            available_pool[color] -= amount
            generic_needed -= amount
            if generic_needed == 0:
                break
        remaining["X"] = generic_needed

        sources = self.select_mana_sources(client, dict(remaining), excluded_permanent)
        if sources is None:
            return None
        return sources, spent_pool

    @staticmethod
    def commit_mana_payment(client, payment_plan):
        sources, spent_pool = payment_plan
        Game.tap_permanents(sources)
        mana_pool = getattr(client, "mana_pool", {}) or {}
        for color, amount in spent_pool.items():
            mana_pool[color] = mana_pool.get(color, 0) - amount
            if mana_pool[color] <= 0:
                mana_pool.pop(color, None)
        client.mana_pool = mana_pool

    def gain_life(self, client, amount):
        if client is None or self.cant_gain_life_this_turn:
            return 0
        client.life_total += amount
        return amount

    def deal_damage_to_player(self, client, amount):
        shield = getattr(client, "damage_prevention_shield", 0)
        prevented = 0 if self.cant_prevent_damage_this_turn else min(shield, amount)
        client.damage_prevention_shield = shield - prevented
        dealt = amount - prevented
        client.life_total -= dealt
        return dealt

    def deal_damage_to_permanent(self, permanent, amount):
        shield = permanent.get("damage_prevention_shield", 0)
        prevented = 0 if self.cant_prevent_damage_this_turn else min(shield, amount)
        permanent["damage_prevention_shield"] = shield - prevented
        dealt = amount - prevented
        permanent["damage"] = permanent.get("damage", 0) + dealt
        return dealt

    @staticmethod
    def tap_permanents(permanents):
        for permanent in permanents:
            permanent["tapped"] = True

    def deal_damage(self, target_id, amount):
        target_client = self.client_for_player(target_id)
        if target_client is not None:
            dealt = self.deal_damage_to_player(target_client, amount)
            return {"type": "DAMAGE", "target": target_id, "amount": dealt}

        _, permanent = self.find_permanent(target_id)
        if isinstance(permanent, dict) and permanent.get("toughness") is not None:
            dealt = self.deal_damage_to_permanent(permanent, amount)
            return {"type": "DAMAGE", "target": target_id, "amount": dealt}
        return None

    def destroy_permanent(self, target_id, allow_regeneration=True):
        owner, permanent = self.find_permanent(target_id)
        if owner is None or permanent is None:
            return None
        if (
            allow_regeneration
            and isinstance(permanent, dict)
            and permanent.get("regeneration_shield")
            and not permanent.get("cant_regenerate")
        ):
            permanent["regeneration_shield"] = False
            permanent["tapped"] = True
            permanent["damage"] = 0
            return {"type": "REGENERATE", "target": target_id}
        owner.battlefield.remove(permanent)
        owner.graveyard.append(target_id)
        return {"type": "DESTROY", "target": target_id}

    def resolve_stack_effect(self, stack_item):
        source_id = stack_item.get("source", "")
        base_id = self.base_card_id(source_id)
        targets = stack_item.get("targets", [])
        target_id = targets[0] if targets else None

        if targets and not self.targets_are_legal(
            source_id, targets, controller_id=stack_item.get("controller")
        ):
            return "FIZZLE", []

        damage_amounts = {

            "lightning_bolt": 3,
            "shock": 2,
            "lava_spike": 3,
            "flame_slash": 4,
            "searing_spear": 3,
            "skullcrack": 3,
            "rift_bolt": 3,
            "incinerate": 3,
            "prodigal_sorcerer": 1,
            "rod_of_ruin": 1,
        }
        if base_id in damage_amounts:
            change = self.deal_damage(target_id, damage_amounts[base_id])
            return (
                ("RESOLVED", [change])
                if change is not None
                else ("FIZZLE", [])
            )

        if base_id in {"counterspell", "cancel", "negate", "mana_leak"}:
            countered_item = next(
                (
                    item
                    for item in self.stack
                    if item.get("stack_item_id") == target_id
                ),
                None,
            )
            if countered_item is None:
                return "FIZZLE", []
            self.stack.remove(countered_item)
            if countered_item.get("item_type") == "SPELL":
                controller = self.client_for_player(countered_item.get("controller"))
                if controller is not None:
                    controller.graveyard.append(countered_item["source"])
            return "RESOLVED", [{"type": "COUNTER", "target": target_id}]

        if base_id == "unsummon":
            owner, permanent = self.find_permanent(target_id)
            if owner is None or permanent is None:
                return "FIZZLE", []
            owner.battlefield.remove(permanent)
            owner.hand.append(target_id)
            return "RESOLVED", [{"type": "RETURN_TO_HAND", "target": target_id}]

        if base_id in {"naturalize", "terror", "doom_blade"}:
            change = self.destroy_permanent(target_id)
            return (
                ("RESOLVED", [change])
                if change is not None
                else ("FIZZLE", [])
            )

        if base_id == "ponder":
            controller = self.client_for_player(stack_item.get("controller"))
            if controller is None or not controller.library:
                return "RESOLVED", []
            drawn_card = controller.library.pop(0)
            controller.hand.append(drawn_card)
            return "RESOLVED", [{"type": "DRAW", "player": controller.pid}]

        return "RESOLVED", []

    def losing_player(self):
        losing_clients = [
            client
            for client in self.clients
            if client.life_total <= 0
        ]
        if not losing_clients:
            return None
        active_client = self.client_for_player(self.active_player)
        if active_client in losing_clients:
            return active_client
        return losing_clients[0]

    def broadcast_game_state(self):
        for client in list(self.clients):
            try:
                self.pdu_dispatcher.send_game_state_update(
                    client,
                    self.state_builder.build_game_state(client)
                )
            except (ConnectionError, OSError):
                self.return_to_lobby(client)
                return False
        return True

    def transition_phase(self, phase):
        previous_phase = self.phase
        self.phase = phase
        for client in list(self.clients):
            try:
                self.pdu_dispatcher.send_phase_transition(
                    client,
                    previous_phase,
                    phase,
                    self.active_player,
                    self.turn
                )
            except (ConnectionError, OSError):
                self.return_to_lobby(client)
                return False
        return True

    def grant_priority(self, player_id):
        client = self.client_for_player(player_id)
        if client is None:
            return False

        self.priority_holder = player_id
        try:
            self.pdu_dispatcher.send_priority_grant(client, player_id)
        except (ConnectionError, OSError):
            self.return_to_lobby(client)
            return False
        return True

    def enter_priority_phase(self, phase):
        self.priority_holder = self.active_player
        self.consecutive_priority_passes = 0
        if not self.transition_phase(phase):
            return False
        if not self.broadcast_game_state():
            return False
        return self.grant_priority(self.active_player)

    def enter_action_phase(self, phase):
        self.priority_holder = None
        self.consecutive_priority_passes = 0
        if not self.transition_phase(phase):
            return False
        return self.broadcast_game_state()

    def open_priority_window(self):
        self.consecutive_priority_passes = 0
        self.priority_holder = self.active_player
        if not self.broadcast_game_state():
            return False
        return self.grant_priority(self.active_player)

    def handle_mulligan_phase(self):
        if not self.transition_phase("MULLIGAN"):
            return False
        for client in list(self.clients):
            try:
                self.pdu_dispatcher.send_game_state_update(
                    client,
                    self.state_builder.build_mulligan_state(client)
                )
            except (ConnectionError, OSError):
                self.return_to_lobby(client)
                return False

        while not all(client.mulligan_kept for client in self.clients):
            if getattr(self, "game_over", False):
                return False
            waiting_clients = {
                client.sock: client
                for client in self.clients
                if not client.mulligan_kept
            }
            readable, _, _ = select.select(waiting_clients, [], [])

            for ready_socket in readable:
                client = waiting_clients[ready_socket]

                try:
                    pdu = client.receive()
                except (ConnectionError, OSError):
                    self.return_to_lobby(client)
                    return False

                self.pdu_dispatcher.handle(client, pdu)
                if getattr(self, "game_over", False):
                    return False

        return True

    def handle_untap_phase(self):
        self.turn += 1
        self.priority_holder = None
        self.land_played_this_turn = {
            client.pid: False
            for client in self.clients
        }

        active_client = self.client_for_player(self.active_player)
        if active_client is None:
            return False
        for permanent in active_client.battlefield:
            if isinstance(permanent, dict):
                permanent["tapped"] = False
                if permanent.get("summoning_sick"):
                    permanent["summoning_sick"] = False

        if not self.transition_phase("UNTAP"):
            return False
        return self.broadcast_game_state()

    def upkeep(self):
        if not self.transition_phase("UPKEEP"):
            return False
        due = [entry for entry in self.suspended_cards if entry["owner"] == self.active_player]
        for entry in due:
            entry["time_counters"] -= 1
            if entry["time_counters"] > 0:
                continue
            owner = self.client_for_player(entry["owner"])
            options = [client.pid for client in self.clients]
            options.extend(
                permanent.get("id")
                for client in self.clients for permanent in client.battlefield
                if isinstance(permanent, dict) and "creature" in (self.card_data(permanent.get("id", "")) or {}).get("card_type", "").casefold()
            )
            def validate_target(pdu, legal=list(options)):
                selected = pdu.get("selected_targets")
                return list(selected) if isinstance(selected, list) and len(selected) == 1 and selected[0] in legal else None
            def cast_suspended(selected, suspended=entry, suspended_owner=owner):
                self.suspended_cards.remove(suspended)
                suspended_owner.exile.remove(suspended["card_id"])
                stack_item = {
                    "stack_item_id": self.pdu_dispatcher._next_stack_item_id(),
                    "item_type": "SPELL", "source": suspended["card_id"],
                    "controller": suspended_owner.pid, "targets": selected,
                    "mana_payment": {}, "suspended": True,
                }
                self.stack.append(stack_item)
                self.pdu_dispatcher.broadcast_stack_push(stack_item)
                self.priority_holder = self.active_player
                events = [GameEvent("spell_cast", {"card_id": suspended["card_id"], "controller": suspended_owner.pid, "targets": selected})]
                events.append(GameEvent("became_target", {"target_id": selected[0], "source": suspended["card_id"], "controller": suspended_owner.pid}))
                return self.post_event(events)
            self.pdu_dispatcher.send_card_choice_request(
                owner, entry["card_id"], "SELECT_TARGETS", "Choose a target for suspended Rift Bolt.",
                1, 1, options, validator=validate_target, continuation=cast_suspended,
            )
            return False
        self.priority_holder = self.active_player
        self.consecutive_priority_passes = 0
        if not self.broadcast_game_state():
            return False
        return self.grant_priority(self.active_player)

    def draw(self):
        if not self.transition_phase("DRAW"):
            return False

        active_client = self.client_for_player(self.active_player)
        if active_client is None:
            return False

        if self.turn != 1:
            if not active_client.library:
                self.end_game(active_client, "DECK_EMPTY")
                return False
            active_client.hand.append(active_client.library.pop(0))

        self.priority_holder = self.active_player
        self.consecutive_priority_passes = 0
        if not self.broadcast_game_state():
            return False
        return self.grant_priority(self.active_player)

    def advance_phase(self):
        next_phases = {
            "UPKEEP": self.draw,
            "DRAW": lambda: self.enter_priority_phase("PRECOMBAT_MAIN"),
            "PRECOMBAT_MAIN": lambda: self.enter_priority_phase("BEGIN_COMBAT"),
            "BEGIN_COMBAT": self.begin_declare_attackers,
            "DECLARE_ATTACKERS": self.begin_declare_blockers,
            "DECLARE_BLOCKERS": self.advance_after_blockers,
            "ASSIGN_DAMAGE_ORDER": self.start_combat_damage,
            "FIRST_STRIKE_DAMAGE": lambda: self.resolve_combat_damage(False),
            "END_OF_COMBAT": lambda: self.enter_priority_phase("POSTCOMBAT_MAIN"),
            "POSTCOMBAT_MAIN": lambda: self.enter_priority_phase("END_STEP"),
            "END_STEP": self.cleanup
        }
        advance = next_phases.get(self.phase)
        if advance is None:
            return False
        return advance()

    def begin_declare_attackers(self):
        self.attackers = []
        self.attackers_declared = False
        return self.enter_action_phase("DECLARE_ATTACKERS")

    def begin_declare_blockers(self):
        self.blockers = []
        self.blockers_declared = False
        return self.enter_action_phase("DECLARE_BLOCKERS")

    def after_attackers_declared(self):
        if not getattr(self, "attackers", []):
            return self.enter_priority_phase("END_OF_COMBAT")
        return self.open_priority_window()

    def after_blockers_declared(self):
        blocker_counts = {}
        for blocker in getattr(self, "blockers", []):
            attacker_id = blocker["blocking_id"]
            blocker_counts[attacker_id] = blocker_counts.get(attacker_id, 0) + 1

        self.damage_orders = {}
        self.pending_damage_orders = {
            attacker_id
            for attacker_id, count in blocker_counts.items()
            if count > 1
        }
        return self.open_priority_window()

    def advance_after_blockers(self):
        if self.pending_damage_orders:
            return self.enter_action_phase("ASSIGN_DAMAGE_ORDER")
        return self.start_combat_damage()

    def after_damage_order(self, attacker_id):
        self.pending_damage_orders.discard(attacker_id)
        if not self.broadcast_game_state():
            return False
        if self.pending_damage_orders:
            return True
        return self.open_priority_window()

    @staticmethod
    def permanent_id(permanent):
        return permanent.get("id") if isinstance(permanent, dict) else permanent

    def find_permanent(self, permanent_id):
        for client in self.clients:
            for permanent in client.battlefield:
                if self.permanent_id(permanent) == permanent_id:
                    return client, permanent
        return None, None

    def is_pacified(self, permanent_id):
        return any(
            isinstance(aura, dict)
            and self.base_card_id(aura.get("id", "")) == "pacifism"
            and aura.get("attached_to") == permanent_id
            for client in self.clients
            for aura in client.battlefield
        )

    @staticmethod
    def permanent_keywords(permanent):
        if not isinstance(permanent, dict):
            return set()
        keywords = {
            str(keyword).casefold().replace("_", " ")
            for keyword in permanent.get("keywords", [])
        }
        if permanent.get("temporary_haste"):
            keywords.add("haste")
        temporary_protection = permanent.get("temporary_protection")
        if temporary_protection:
            keywords.add(f"protection from {temporary_protection}")
        return keywords

    @staticmethod
    def basic_land_ids(cards, card_lookup):
        return [
            card_id for card_id in cards
            if "basic" in (card_lookup(card_id) or {}).get("subtype", "").casefold()
            and "land" in (card_lookup(card_id) or {}).get("card_type", "").casefold()
        ]

    @staticmethod
    def exact_card_selection_validator(options, count):
        offered = list(options)
        def validate(pdu):
            selected = pdu.get("selected_cards")
            if not isinstance(selected, list) or len(selected) != count:
                return None
            if len(set(selected)) != len(selected) or any(card not in offered for card in selected):
                return None
            return list(selected)
        return validate

    def is_protected_from(self, target_permanent, source_permanent):
        if not isinstance(target_permanent, dict) or not isinstance(source_permanent, dict):
            return False
        source_data = self.card_data(source_permanent.get("id", "")) or {}
        source_color = {
            "W": "white", "U": "blue", "B": "black", "R": "red", "G": "green",
        }.get(str(source_data.get("color", "")).upper(), "")
        return f"protection from {source_color}" in self.permanent_keywords(target_permanent)

    def start_combat_damage(self):
        if self.combat_has_first_strike():
            return self.resolve_combat_damage(True)
        return self.resolve_combat_damage(False)

    def combat_has_first_strike(self):
        combat_ids = {
            attacker["creature_id"]
            for attacker in getattr(self, "attackers", [])
        }
        combat_ids.update(
            blocker["creature_id"]
            for blocker in getattr(self, "blockers", [])
        )
        for permanent_id in combat_ids:
            _, permanent = self.find_permanent(permanent_id)
            keywords = self.permanent_keywords(permanent)
            if "first strike" in keywords or "double strike" in keywords:
                return True
        return False

    def post_event(self, events=None, sba_result=None):
        """Canonical post-event pipeline per MTG rules & RFC requirements."""
        batch_id = self.trigger_manager.generate_batch_id() if events is not None else None
        if events is not None:
            event_list = events if isinstance(events, list) else [events]
            for event in event_list:
                self.event_bus.publish(event)
                for trg in self.trigger_manager.detect_triggers_for_event(event):
                    trg.batch_id = trg.batch_id or batch_id
                    self.trigger_manager.pending_triggers.append(trg)

        # 1. Run State-Based Actions
        if sba_result is None:
            changes, game_over_info = StateBasedActions.check_and_apply(self)
        else:
            changes, game_over_info = sba_result
        for change in changes:
            if change.get("type") == "CREATURE_DIED":
                death_event = GameEvent("creature_died", change)
                self.event_bus.publish(death_event)
                for trg in self.trigger_manager.detect_triggers_for_event(death_event):
                    trg.batch_id = trg.batch_id or batch_id or self.trigger_manager.generate_batch_id()
                    self.trigger_manager.pending_triggers.append(trg)

        # Ensure all unbatched pending triggers share a single batch_id
        unbatched = [t for t in self.trigger_manager.pending_triggers if not getattr(t, "batch_id", None)]
        if unbatched:
            shared_bid = self.trigger_manager.generate_batch_id()
            for trg in unbatched:
                trg.batch_id = shared_bid

        # 2. Check Game Over
        if game_over_info is not None:
            winner_c = self.client_for_player(game_over_info["winner_id"])
            loser_c = self.other_client(winner_c) if winner_c else self.clients[0] if self.clients else None
            return self.end_game(loser_c, game_over_info["reason"])

        # 3. Process Pending Triggers into stack items
        if self.has_pending_decision():
            self.pdu_dispatcher._broadcast_game_state()
            return False

        ap = self.active_player
        nap = self.other_player(ap) if ap else None
        ap_client = self.client_for_player(ap) if ap else None
        nap_client = self.client_for_player(nap) if nap else None

        # Identify distinct un-ordered batches
        distinct_batches = []
        for t in self.trigger_manager.pending_triggers:
            bid = getattr(t, "batch_id", None)
            if bid and bid not in distinct_batches:
                distinct_batches.append(bid)

        for bid in distinct_batches:
            batch_trgs = [t for t in self.trigger_manager.pending_triggers if getattr(t, "batch_id", None) == bid]
            ap_trgs = [t for t in batch_trgs if t.controller == ap]
            nap_trgs = [t for t in batch_trgs if t.controller == nap]

            if len(ap_trgs) > 1 and (bid, ap) not in self.trigger_manager.ordered_batches:
                if ap_client and not getattr(ap_client, "pending_trigger_ids", None):
                    self.pdu_dispatcher.send_trigger_order_prompt(ap_client, ap, [t.trigger_id for t in ap_trgs])
                    self.pdu_dispatcher._broadcast_game_state()
                    return False

            if len(nap_trgs) > 1 and (bid, nap) not in self.trigger_manager.ordered_batches:
                if nap_client and not getattr(nap_client, "pending_trigger_ids", None):
                    self.pdu_dispatcher.send_trigger_order_prompt(nap_client, nap, [t.trigger_id for t in nap_trgs])
                    self.pdu_dispatcher._broadcast_game_state()
                    return False

        # Sort pending triggers batch-by-batch: AP first, NAP second (on top)
        new_pending = []
        for bid in distinct_batches:
            batch_trgs = [t for t in self.trigger_manager.pending_triggers if getattr(t, "batch_id", None) == bid]
            b_ap = [t for t in batch_trgs if t.controller == ap]
            b_nap = [t for t in batch_trgs if t.controller == nap]
            b_other = [t for t in batch_trgs if t.controller not in (ap, nap)]
            new_pending.extend(b_ap + b_nap + b_other)
        remaining_unbatched = [t for t in self.trigger_manager.pending_triggers if not getattr(t, "batch_id", None)]
        self.trigger_manager.pending_triggers = new_pending + remaining_unbatched

        while self.trigger_manager.pending_triggers:
            trg = self.trigger_manager.pending_triggers[0]
            if trg.requires_target:
                if trg.legal_targets:
                    ctrl_client = self.client_for_player(trg.controller)
                    if ctrl_client:
                        self.pdu_dispatcher.send_trigger_choice_prompt(ctrl_client, trg)
                        self.pdu_dispatcher._broadcast_game_state()
                        return False
                else:
                    self.trigger_manager.pending_triggers.pop(0)
                    continue

            self.trigger_manager.pending_triggers.pop(0)
            stack_item = {
                "stack_item_id": self.pdu_dispatcher._next_stack_item_id(),
                "item_type": "TRIGGER_ABILITY",
                "trigger_id": trg.trigger_id,
                "source": trg.source_id,
                "controller": trg.controller,
                "effect_summary": trg.effect_summary,
                "effect_fn": trg.effect_fn
            }
            self.stack.append(stack_item)
            self.pdu_dispatcher.broadcast_stack_push(stack_item)

        # 4. Broadcast updated game state
        self.pdu_dispatcher._broadcast_game_state()

        continuation = self.pending_event_continuation
        if continuation is not None:
            self.pending_event_continuation = None
            return continuation()

        # 5. Grant priority ONLY when no mandatory decision is pending
        if self.priority_holder and not self.has_pending_decision():
            client = self.client_for_player(self.priority_holder)
            if client:
                self.pdu_dispatcher.send_priority_grant(client, self.priority_holder)

        return True

    def has_pending_decision(self) -> bool:
        if bool(getattr(self, "pending_damage_orders", None)):
            return True
        for client in getattr(self, "clients", []):
            if getattr(client, "pending_card_choice", None) is not None:
                return True
            if getattr(client, "pending_trigger_choice", None) is not None:
                return True
            if getattr(client, "pending_trigger_ids", None) is not None:
                return True
        return False

    def has_pending_card_choice(self) -> bool:
        return any(
            getattr(client, "pending_card_choice", None) is not None
            for client in getattr(self, "clients", [])
        )

    def other_player(self, player_id: str) -> Optional[str]:
        for c in self.clients:
            if c.pid != player_id:
                return c.pid
        return None

    def resolve_top_stack_item(self):
        if not self.stack:
            return False
        item = self.stack.pop()
        item_type = item.get("item_type")
        source_id = item.get("source", "")
        controller = item.get("controller", "")
        targets = item.get("targets", [])

        ctrl_client = self.client_for_player(controller)
        opp_client = self.other_client(ctrl_client) if ctrl_client else None
        resolution_events = None

        # Both passes clear the old holder. Every completed stack resolution
        # starts a fresh priority window with the active player.
        self.priority_holder = self.active_player

        if item_type == "TRIGGER_ABILITY":
            fn = item.get("effect_fn")
            if callable(fn):
                fn(item, self)
            self.pdu_dispatcher.broadcast_stack_resolve(item.get("stack_item_id"), "RESOLVED", [])
        elif item_type == "ABILITY":
            base_id = self.base_card_id(source_id)
            if targets and not self.targets_are_legal(
                source_id, targets, is_ability=True, controller_id=controller
            ):
                self.pdu_dispatcher.broadcast_stack_resolve(item.get("stack_item_id"), "FIZZLE", [])
                return self.post_event()

            if base_id == "merfolk_looter":
                if ctrl_client.library:
                    ctrl_client.hand.append(ctrl_client.library.pop(0))
                options = list(ctrl_client.hand)
                count = min(1, len(options))
                if count:
                    def finish_loot(selected):
                        card_id = selected[0]
                        ctrl_client.hand.remove(card_id)
                        ctrl_client.graveyard.append(card_id)
                        self.pdu_dispatcher.broadcast_stack_resolve(item["stack_item_id"], "RESOLVED", [
                            {"type": "DRAW_DISCARD", "player": controller}
                        ])
                        return self.post_event()
                    self.pdu_dispatcher.send_card_choice_request(
                        ctrl_client, source_id, "SELECT_CARDS", "Choose one card to discard.",
                        1, 1, options,
                        validator=self.exact_card_selection_validator(options, 1),
                        continuation=finish_loot,
                    )
                    return False
            elif base_id == "mother_of_runes":
                colors = ["WHITE", "BLUE", "BLACK", "RED", "GREEN"]
                def validate_color(pdu):
                    color = pdu.get("color")
                    return color if color in colors else None
                def finish_mother(color):
                    _, permanent = self.find_permanent(targets[0])
                    if permanent:
                        permanent["temporary_protection"] = color.casefold()
                    self.pdu_dispatcher.broadcast_stack_resolve(item["stack_item_id"], "RESOLVED", [
                        {"type": "TEMP_PROTECTION", "target": targets[0], "color": color}
                    ])
                    return self.post_event()
                self.pdu_dispatcher.send_card_choice_request(
                    ctrl_client, source_id, "COLOR", "Choose a protection color.",
                    1, 1, colors, validator=validate_color, continuation=finish_mother,
                )
                return False

            status, changes = CardEffects.resolve_ability_effect(base_id, source_id, targets, ctrl_client, opp_client, self)
            self.pdu_dispatcher.broadcast_stack_resolve(item.get("stack_item_id"), status, changes)
        elif item_type == "SPELL":
            base_id = self.base_card_id(source_id)
            if targets and not self.targets_are_legal(
                source_id, targets, controller_id=controller, mode=item.get("mode")
            ):
                # Spell FIZZLES
                if ctrl_client:
                    ctrl_client.graveyard.append(source_id)
                self.pdu_dispatcher.broadcast_stack_resolve(item.get("stack_item_id"), "FIZZLE", [])
                return self.post_event()

            def finish_choice_spell(changes):
                if ctrl_client and source_id not in ctrl_client.graveyard:
                    ctrl_client.graveyard.append(source_id)
                self.pdu_dispatcher.broadcast_stack_resolve(item["stack_item_id"], "RESOLVED", changes)
                return self.post_event()

            if base_id == "ponder":
                viewed = list(ctrl_client.library[:3])
                if not viewed:
                    return finish_choice_spell([])
                def finish_ponder(answer):
                    if answer[0]:
                        getattr(self, "rng", random).shuffle(ctrl_client.library)
                    drawn = ctrl_client.library.pop(0) if ctrl_client.library else None
                    if drawn is not None:
                        ctrl_client.hand.append(drawn)
                    return finish_choice_spell([{"type": "DRAW", "player": controller}])
                def request_shuffle(ordered):
                    ctrl_client.library[:len(viewed)] = ordered
                    self.pdu_dispatcher.send_card_choice_request(
                        ctrl_client, source_id, "YES_NO", "Shuffle your library?",
                        1, 1, [True, False],
                        validator=lambda pdu: (pdu.get("answer"),) if isinstance(pdu.get("answer"), bool) else None,
                        continuation=finish_ponder,
                    )
                    return False
                def validate_order(pdu):
                    ordered = pdu.get("ordered_cards")
                    if not isinstance(ordered, list) or len(ordered) != len(viewed):
                        return None
                    if len(set(ordered)) != len(ordered) or sorted(ordered) != sorted(viewed):
                        return None
                    return list(ordered)
                self.pdu_dispatcher.send_card_choice_request(
                    ctrl_client, source_id, "ORDER_CARDS", "Order the cards from top to bottom.",
                    len(viewed), len(viewed), viewed,
                    validator=validate_order, continuation=request_shuffle,
                )
                return False

            if base_id == "mana_leak":
                target_item = next(
                    (candidate for candidate in self.stack if candidate.get("stack_item_id") == targets[0]),
                    None,
                )
                if target_item is None:
                    if ctrl_client:
                        ctrl_client.graveyard.append(source_id)
                    self.pdu_dispatcher.broadcast_stack_resolve(item["stack_item_id"], "FIZZLE", [])
                    return self.post_event()
                target_controller = self.client_for_player(target_item.get("controller"))
                def validate_mana_leak(pdu):
                    pay = pdu.get("pay")
                    if not isinstance(pay, bool):
                        return None
                    if not pay:
                        return (False, None)
                    payment = self.normalize_mana_payment(pdu.get("mana_payment"))
                    if payment != {"X": 3}:
                        return None
                    plan = self.plan_mana_payment(target_controller, payment)
                    return (True, plan) if plan is not None else None
                def finish_mana_leak(decision):
                    pay, plan = decision
                    changes = []
                    if pay:
                        self.commit_mana_payment(target_controller, plan)
                        changes.append({"type": "PAY_MANA", "player": target_controller.pid, "amount": 3})
                    else:
                        self.stack.remove(target_item)
                        if target_item.get("item_type") == "SPELL":
                            target_controller.graveyard.append(target_item.get("source"))
                        changes.append({"type": "COUNTER_SPELL", "stack_item_id": targets[0]})
                    return finish_choice_spell(changes)
                self.pdu_dispatcher.send_card_choice_request(
                    target_controller, source_id, "PAY_MANA", "Pay 3 mana to prevent the spell from being countered?",
                    0, 1, [], required_mana={"Generic": 3},
                    validator=validate_mana_leak, continuation=finish_mana_leak,
                )
                return False

            if base_id == "mind_rot":
                target_client = self.client_for_player(targets[0])
                options = list(target_client.hand)
                count = min(2, len(options))
                if count == 0:
                    return finish_choice_spell([])
                def finish_mind_rot(selected):
                    for card_id in selected:
                        target_client.hand.remove(card_id)
                        target_client.graveyard.append(card_id)
                    return finish_choice_spell([{"type": "DISCARD", "player": target_client.pid, "count": len(selected)}])
                self.pdu_dispatcher.send_card_choice_request(
                    target_client, source_id, "SELECT_CARDS", f"Choose {count} card(s) to discard.",
                    count, count, options,
                    validator=self.exact_card_selection_validator(options, count),
                    continuation=finish_mind_rot,
                )
                return False

            if base_id == "healing_salve":
                mode = item.get("mode")
                target_id = targets[0]
                changes = []
                if mode == "GAIN_LIFE":
                    target_client = self.client_for_player(target_id)
                    gained = self.gain_life(target_client, 3)
                    changes.append({"type": "LIFE_GAIN", "target": target_id, "amount": gained})
                else:
                    target_client = self.client_for_player(target_id)
                    if target_client is not None:
                        target_client.damage_prevention_shield = getattr(target_client, "damage_prevention_shield", 0) + 3
                    else:
                        _, target_permanent = self.find_permanent(target_id)
                        target_permanent["damage_prevention_shield"] = target_permanent.get("damage_prevention_shield", 0) + 3
                    changes.append({"type": "DAMAGE_PREVENTION_SHIELD", "target": target_id, "amount": 3})
                return finish_choice_spell(changes)

            if base_id == "rampant_growth":
                options = self.basic_land_ids(ctrl_client.library, self.card_data)
                if not options:
                    randomizer = getattr(self, "rng", random)
                    randomizer.shuffle(ctrl_client.library)
                    return finish_choice_spell([])
                def finish_growth(selected):
                    card_id = selected[0]
                    ctrl_client.library.remove(card_id)
                    ctrl_client.battlefield.append({"id": card_id, "tapped": True})
                    getattr(self, "rng", random).shuffle(ctrl_client.library)
                    return finish_choice_spell([{"type": "SEARCH_LAND", "player": controller}])
                self.pdu_dispatcher.send_card_choice_request(
                    ctrl_client, source_id, "SELECT_CARDS", "Choose a basic land.",
                    1, 1, options,
                    validator=self.exact_card_selection_validator(options, 1),
                    continuation=finish_growth,
                )
                return False

            if base_id == "path_to_exile":
                owner, permanent = self.find_permanent(targets[0])
                changes = []
                if owner and permanent:
                    owner.battlefield.remove(permanent)
                    owner.exile.append(targets[0])
                    changes.append({"type": "EXILE", "target": targets[0]})
                if owner is None:
                    return finish_choice_spell(changes)
                def finish_path_search(selected):
                    if selected:
                        land_id = selected[0]
                        owner.library.remove(land_id)
                        owner.battlefield.append({"id": land_id, "tapped": True})
                    getattr(self, "rng", random).shuffle(owner.library)
                    return finish_choice_spell(changes + ([{"type": "SEARCH_LAND", "player": owner.pid}] if selected else []))
                def finish_path_yes_no(answer):
                    answer = answer[0]
                    if not answer:
                        return finish_choice_spell(changes)
                    options = self.basic_land_ids(owner.library, self.card_data)
                    if not options:
                        getattr(self, "rng", random).shuffle(owner.library)
                        return finish_choice_spell(changes)
                    self.pdu_dispatcher.send_card_choice_request(
                        owner, source_id, "SELECT_CARDS", "Choose a basic land.",
                        1, 1, options,
                        validator=self.exact_card_selection_validator(options, 1),
                        continuation=finish_path_search,
                    )
                    return False
                self.pdu_dispatcher.send_card_choice_request(
                    owner, source_id, "YES_NO", "Search your library for a basic land?",
                    1, 1, [True, False],
                    validator=lambda pdu: (pdu.get("answer"),) if isinstance(pdu.get("answer"), bool) else None,
                    continuation=finish_path_yes_no,
                )
                return False

            status, changes = CardEffects.resolve_card_effect(
                base_id, source_id, targets, ctrl_client, opp_client, self,
                kicked=bool(item.get("kicked")),
            )
            card_data = self.card_data(source_id) or {}
            card_type = card_data.get("card_type", "").casefold()

            if "creature" in card_type or "artifact" in card_type or "enchantment" in card_type:
                if ctrl_client:
                    perm = {
                        "id": source_id,
                        "tapped": False,
                        "summoning_sick": "creature" in card_type,
                        "power": card_data.get("power", 0),
                        "toughness": card_data.get("toughness", 0),
                        "keywords": card_data.get("keywords", []),
                        "damage": 0
                    }
                    if base_id == "pacifism" and targets:
                        perm["attached_to"] = targets[0]
                    ctrl_client.battlefield.append(perm)
                    resolution_events = GameEvent(
                        "permanent_entered",
                        {"creature_id": source_id, "controller": controller, "kicked": bool(item.get("kicked"))},
                    )
            else:
                if ctrl_client:
                    ctrl_client.graveyard.append(source_id)

            self.pdu_dispatcher.broadcast_stack_resolve(item.get("stack_item_id"), status, changes)

        return self.post_event(resolution_events)

    def get_effective_pt(self, permanent):
        if not isinstance(permanent, dict):
            return 0, 0
        p = permanent.get("power", 0) + permanent.get("temp_power_buff", 0)
        t = permanent.get("toughness", 0) + permanent.get("temp_toughness_buff", 0)
        return max(0, p), max(0, t)

    def enter_end_of_combat_after_damage(self):
        self.priority_holder = self.active_player
        self.consecutive_priority_passes = 0
        if not self.transition_phase("END_OF_COMBAT"):
            return False
        return self.grant_priority(self.active_player)

    def resolve_combat_damage(self, first_strike):
        phase = "FIRST_STRIKE_DAMAGE" if first_strike else "COMBAT_DAMAGE"
        self.priority_holder = None
        if not self.transition_phase(phase):
            return False

        damage_events = []
        for attacker in getattr(self, "attackers", []):
            attacker_id = attacker["creature_id"]
            _, attacker_permanent = self.find_permanent(attacker_id)
            if not isinstance(attacker_permanent, dict):
                continue

            attacker_keywords = self.permanent_keywords(attacker_permanent)
            attacker_eligible = (
                "first strike" in attacker_keywords
                or "double strike" in attacker_keywords
            ) if first_strike else (
                "first strike" not in attacker_keywords
                or "double strike" in attacker_keywords
            )

            attacker_power, _ = self.get_effective_pt(attacker_permanent)

            assigned_blockers = [
                blocker
                for blocker in getattr(self, "blockers", [])
                if blocker["blocking_id"] == attacker_id
            ]

            if not assigned_blockers and attacker_eligible and attacker_power > 0:
                target_client = self.client_for_player(attacker["target"])
                if target_client is not None:
                    dealt = self.deal_damage_to_player(target_client, attacker_power)
                    damage_events.append({
                        "source": attacker_id,
                        "target": target_client.pid,
                        "amount": dealt
                    })
                continue

            order = self.damage_orders.get(
                attacker_id,
                [blocker["creature_id"] for blocker in assigned_blockers]
            )
            remaining_damage = attacker_power if attacker_eligible else 0

            for idx, blocker_id in enumerate(order):
                _, blocker_permanent = self.find_permanent(blocker_id)
                if not isinstance(blocker_permanent, dict):
                    continue

                _, b_toughness = self.get_effective_pt(blocker_permanent)
                lethal = max(0, b_toughness - blocker_permanent.get("damage", 0))

                # Final blocker receives ALL remaining attacker damage per MTGNP rules
                if idx == len(order) - 1:
                    assigned_damage = remaining_damage
                else:
                    assigned_damage = min(remaining_damage, lethal)

                if assigned_damage > 0:
                    remaining_damage -= assigned_damage
                    if not self.is_protected_from(blocker_permanent, attacker_permanent):
                        dealt = self.deal_damage_to_permanent(blocker_permanent, assigned_damage)
                        damage_events.append({
                            "source": attacker_id,
                            "target": blocker_id,
                            "amount": dealt
                        })

            for blocker in assigned_blockers:
                blocker_id = blocker["creature_id"]
                _, blocker_permanent = self.find_permanent(blocker_id)
                if isinstance(blocker_permanent, dict):
                    blocker_keywords = self.permanent_keywords(blocker_permanent)
                    blocker_eligible = (
                        "first strike" in blocker_keywords
                        or "double strike" in blocker_keywords
                    ) if first_strike else (
                        "first strike" not in blocker_keywords
                        or "double strike" in blocker_keywords
                    )
                    if blocker_eligible and not self.is_protected_from(attacker_permanent, blocker_permanent):
                        b_power, _ = self.get_effective_pt(blocker_permanent)
                        dealt = self.deal_damage_to_permanent(attacker_permanent, b_power)
                        if b_power > 0:
                            damage_events.append({
                                "source": blocker_id,
                                "target": attacker_id,
                                "amount": dealt
                            })

        sba_result = StateBasedActions.check_and_apply(self)
        sba_changes, game_over_info = sba_result
        creatures_died = [
            change["card_id"]
            for change in sba_changes
            if change.get("type") == "CREATURE_DIED"
        ]
        life_totals = {
            client.pid: client.life_total
            for client in self.clients
        }
        self.pdu_dispatcher.broadcast_combat_damage_result(
            damage_events,
            life_totals,
            creatures_died,
            game_over_info,
        )

        if first_strike:
            self.priority_holder = self.active_player
        else:
            self.priority_holder = None
            self.pending_event_continuation = self.enter_end_of_combat_after_damage
        return self.post_event(
            GameEvent("combat_damage_dealt", {"damage_events": damage_events}),
            sba_result=sba_result,
        )

    def cleanup(self):
        self.priority_holder = None
        if not self.transition_phase("CLEANUP"):
            return False
        if not self.broadcast_game_state():
            return False

        active_client = self.client_for_player(self.active_player)
        if active_client is None:
            return False
        if len(active_client.hand) > 7:
            return self.enter_action_phase("CLEANUP")
        return self.finish_cleanup()

    def finish_cleanup(self):

        self.cant_gain_life_this_turn = False
        self.cant_prevent_damage_this_turn = False
        for client in self.clients:
            client.mana_pool = {}
            client.damage_prevention_shield = 0
            for permanent in client.battlefield:
                if isinstance(permanent, dict):
                    permanent["damage"] = 0
                    permanent["temp_power_buff"] = 0
                    permanent["temp_toughness_buff"] = 0
                    permanent["cant_regenerate"] = False
                    permanent["regeneration_shield"] = False
                    permanent.pop("opponent_targeting_blocked_until_eot", None)
                    permanent.pop("temporary_haste", None)
                    permanent.pop("temporary_protection", None)
                    permanent.pop("damage_prevention_shield", None)

        active_client = self.client_for_player(self.active_player)
        next_client = self.other_client(active_client)
        if next_client is None:
            return False

        self.active_player = next_client.pid
        self.attackers = []
        self.blockers = []
        self.damage_orders = {}
        self.attackers_declared = False
        self.blockers_declared = False
        self.pending_damage_orders = set()

        if not self.handle_untap_phase():
            return False
        return self.upkeep()




    def check_priority_timeout(self) -> bool:
        if self.priority_holder:
            p_client = self.client_for_player(self.priority_holder)
            if p_client and getattr(p_client, "priority_deadline", None) is not None:
                if time.monotonic() > p_client.priority_deadline:
                    print(f"Priority deadline expired for {p_client.pid}")
                    self.end_game(p_client, "DISCONNECT")
                    return True
        return False

    def end_game(self, losing_client, reason):
        winning_client = self.other_client(losing_client)
        winner_id = winning_client.pid if winning_client is not None else None
        loser_id = losing_client.pid if losing_client else None
        self.priority_holder = None
        self.transition_phase("GAME_OVER")
        self.game_over = True
        for client in list(self.clients):
            client.ready_in_lobby = False
            try:
                self.pdu_dispatcher.send_game_over(
                    client,
                    winner_id,
                    loser_id,
                    reason
                )
            except (ConnectionError, OSError):
                pass
        if reason == "DISCONNECT":
            self.connection.return_to_lobby(disconnected_client=losing_client)
        else:
            self.connection.return_to_lobby(disconnected_client=None)
        return True

    def run_game_loop(self):
        """Run mulligans, enter the first turn, then dispatch game actions."""

        if len(self.clients) != self.max_clients:
            raise RuntimeError("The game cannot start until the lobby is full.")

        if not self.game_setup():
            return

        if not self.handle_mulligan_phase():
            return

        if not self.handle_untap_phase():
            return
        if not self.upkeep():
            return

        while self.clients and not self.game_over:
            self.connection.refuse_extra_connections()

            # Check server priority deadline
            if self.check_priority_timeout():
                break

            sockets = [client.sock for client in self.clients]
            readable, _, _ = select.select(sockets, [], [], 0.1)

            for ready_socket in readable:
                client = next(
                    player
                    for player in self.clients
                    if player.sock is ready_socket
                )
                try:
                    pdu = client.receive()
                    self.pdu_dispatcher.handle(client, pdu)
                except (ConnectionError, OSError):
                    self.end_game(client, "DISCONNECT")
                    return
                except (json.JSONDecodeError, UnicodeDecodeError):
                    from app.server.pdu_dispatcher import MSG_INVALID_JSON, ERR_INVALID_JSON
                    self.pdu_dispatcher.send_error(client, MSG_INVALID_JSON, ERR_INVALID_JSON)


