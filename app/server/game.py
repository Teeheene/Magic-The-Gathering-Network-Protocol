import select
import random
import re
from collections import Counter
from pathlib import Path

from app.server.pdu_dispatcher import PduDispatcher
from app.server.game_state import StateBuilder
from app.shared.card_catalog import CardCatalog


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
        self.next_stack_item_id = 1
        self.game_over = False

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
        self.game_over = False

        rng = getattr(self, "rng", random)
        self.active_player = rng.choice(self.clients).pid
        for client in self.clients:
            deck = list(client.deck_list)
            rng.shuffle(deck)
            client.hand = deck[:7]
            client.library = deck[7:]
            client.life_total = 20
            client.battlefield = []
            client.graveyard = []
            client.mulligan_taken = 0
            client.mulligan_kept = False

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

    def targets_are_legal(self, card_id, targets):
        card_data = self.card_data(card_id) or {}
        requires_target = "target" in card_data.get("text", "").casefold()
        if not requires_target:
            return not targets
        return len(targets) == 1 and self.target_exists(targets[0])

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

    @staticmethod
    def tap_permanents(permanents):
        for permanent in permanents:
            permanent["tapped"] = True

    def deal_damage(self, target_id, amount):
        target_client = self.client_for_player(target_id)
        if target_client is not None:
            target_client.life_total -= amount
            return {"type": "DAMAGE", "target": target_id, "amount": amount}

        _, permanent = self.find_permanent(target_id)
        if isinstance(permanent, dict) and permanent.get("toughness") is not None:
            permanent["damage"] = permanent.get("damage", 0) + amount
            return {"type": "DAMAGE", "target": target_id, "amount": amount}
        return None

    def destroy_permanent(self, target_id):
        owner, permanent = self.find_permanent(target_id)
        if owner is None or permanent is None:
            return None
        owner.battlefield.remove(permanent)
        owner.graveyard.append(target_id)
        return {"type": "DESTROY", "target": target_id}

    def resolve_stack_effect(self, stack_item):
        source_id = stack_item.get("source", "")
        base_id = self.base_card_id(source_id)
        targets = stack_item.get("targets", [])
        target_id = targets[0] if targets else None

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

                self.pdu_dispatcher.handle_mulligan_choice(client, pdu)

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
        return self.enter_priority_phase("UPKEEP")

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

    @staticmethod
    def permanent_keywords(permanent):
        if not isinstance(permanent, dict):
            return set()
        return {
            str(keyword).casefold().replace("_", " ")
            for keyword in permanent.get("keywords", [])
        }

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

    def start_combat_damage(self):
        if self.combat_has_first_strike():
            return self.resolve_combat_damage(True)
        return self.resolve_combat_damage(False)

    def resolve_combat_damage(self, first_strike):
        phase = "FIRST_STRIKE_DAMAGE" if first_strike else "COMBAT_DAMAGE"
        self.priority_holder = None
        if not self.transition_phase(phase):
            return False

        damage_events = []
        for attacker in getattr(self, "attackers", []):
            attacker_id = attacker["creature_id"]
            _, attacker_permanent = self.find_permanent(attacker_id)
            attacker_keywords = self.permanent_keywords(attacker_permanent)
            attacker_eligible = (
                "first strike" in attacker_keywords
                or "double strike" in attacker_keywords
            ) if first_strike else (
                "first strike" not in attacker_keywords
                or "double strike" in attacker_keywords
            )
            attacker_power = (
                attacker_permanent.get("power", 0)
                if isinstance(attacker_permanent, dict)
                else 0
            )
            assigned_blockers = [
                blocker
                for blocker in getattr(self, "blockers", [])
                if blocker["blocking_id"] == attacker_id
            ]

            if not assigned_blockers and attacker_eligible and attacker_power > 0:
                target_client = self.client_for_player(attacker["target"])
                if target_client is not None:
                    target_client.life_total -= attacker_power
                    damage_events.append({
                        "source": attacker_id,
                        "target": target_client.pid,
                        "amount": attacker_power
                    })
                continue

            order = self.damage_orders.get(
                attacker_id,
                [blocker["creature_id"] for blocker in assigned_blockers]
            )
            remaining_damage = attacker_power if attacker_eligible else 0
            for blocker_id in order:
                _, blocker_permanent = self.find_permanent(blocker_id)
                if not isinstance(blocker_permanent, dict):
                    continue
                lethal = max(
                    0,
                    blocker_permanent.get("toughness", 0)
                    - blocker_permanent.get("damage", 0)
                )
                assigned_damage = min(remaining_damage, lethal)
                if assigned_damage:
                    blocker_permanent["damage"] = (
                        blocker_permanent.get("damage", 0) + assigned_damage
                    )
                    remaining_damage -= assigned_damage
                    damage_events.append({
                        "source": attacker_id,
                        "target": blocker_id,
                        "amount": assigned_damage
                    })

            if isinstance(attacker_permanent, dict):
                for blocker in assigned_blockers:
                    blocker_id = blocker["creature_id"]
                    _, blocker_permanent = self.find_permanent(blocker_id)
                    blocker_keywords = self.permanent_keywords(blocker_permanent)
                    blocker_eligible = (
                        "first strike" in blocker_keywords
                        or "double strike" in blocker_keywords
                    ) if first_strike else (
                        "first strike" not in blocker_keywords
                        or "double strike" in blocker_keywords
                    )
                    if blocker_eligible and isinstance(blocker_permanent, dict):
                        damage = blocker_permanent.get("power", 0)
                        attacker_permanent["damage"] = (
                            attacker_permanent.get("damage", 0) + damage
                        )
                        if damage:
                            damage_events.append({
                                "source": blocker_id,
                                "target": attacker_id,
                                "amount": damage
                            })

        creatures_died = self.remove_lethally_damaged_creatures()
        life_totals = {
            client.pid: client.life_total
            for client in self.clients
        }
        for client in self.clients:
            self.pdu_dispatcher.send_combat_damage_result(
                client,
                damage_events,
                life_totals,
                creatures_died
            )

        losing_client = next(
            (client for client in self.clients if client.life_total <= 0),
            None,
        )
        if losing_client is not None:
            return self.end_game(losing_client, "LIFE_ZERO")

        if not self.broadcast_game_state():
            return False

        if first_strike:
            self.consecutive_priority_passes = 0
            return self.grant_priority(self.active_player)
        return self.enter_priority_phase("END_OF_COMBAT")

    def remove_lethally_damaged_creatures(self):
        creatures_died = []
        for client in self.clients:
            survivors = []
            for permanent in client.battlefield:
                lethal = (
                    isinstance(permanent, dict)
                    and permanent.get("toughness") is not None
                    and permanent.get("damage", 0) >= permanent["toughness"]
                )
                if lethal:
                    card_id = permanent["id"]
                    creatures_died.append(card_id)
                    client.graveyard.append(card_id)
                else:
                    survivors.append(permanent)
            client.battlefield = survivors
        return creatures_died

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
            return True
        return self.finish_cleanup()

    def finish_cleanup(self):
        for client in self.clients:
            for permanent in client.battlefield:
                if isinstance(permanent, dict):
                    permanent["damage"] = 0

        if not self.broadcast_game_state():
            return False

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

    def resolve_top_stack_item(self):
        if not self.stack:
            return False

        stack_item = self.stack.pop()
        result = "RESOLVED"
        state_changes = []
        if stack_item.get("item_type") == "SPELL":
            controller = self.client_for_player(stack_item.get("controller"))
            if controller is not None:
                source_id = stack_item["source"]
                card_data = self.card_data(source_id) or {}
                card_type = card_data.get("card_type", "").casefold()
                if any(
                    permanent_type in card_type
                    for permanent_type in ("creature", "artifact", "enchantment")
                ):
                    permanent = {"id": source_id, "tapped": False}
                    if "creature" in card_type:
                        permanent.update({
                            "power": card_data.get("power", 0),
                            "toughness": card_data.get("toughness", 0),
                            "damage": 0,
                            "summoning_sick": True,
                            "keywords": list(card_data.get("keywords", [])),
                        })
                    controller.battlefield.append(permanent)
                    state_changes.append({
                        "type": "PERMANENT_ENTERS",
                        "card_id": source_id,
                        "controller": controller.pid,
                        "tapped": False,
                    })
                else:
                    result, state_changes = self.resolve_stack_effect(stack_item)
                    controller.graveyard.append(source_id)
        elif stack_item.get("item_type") == "ABILITY":
            result, state_changes = self.resolve_stack_effect(stack_item)

        creatures_died = self.remove_lethally_damaged_creatures()
        state_changes.extend(
            {"type": "DESTROY", "target": creature_id}
            for creature_id in creatures_died
        )

        for client in self.clients:
            self.pdu_dispatcher.send_stack_resolve(
                client,
                stack_item["stack_item_id"],
                result,
                state_changes
            )
        if not self.broadcast_game_state():
            return False

        losing_client = self.losing_player()
        if losing_client is not None:
            return self.end_game(losing_client, "LIFE_ZERO")

        self.consecutive_priority_passes = 0
        return self.grant_priority(self.active_player)

    def end_game(self, losing_client, reason):
        winning_client = self.other_client(losing_client)
        winner_id = winning_client.pid if winning_client is not None else None
        self.priority_holder = None
        if not self.transition_phase("GAME_OVER"):
            return False
        self.game_over = True
        for client in self.clients:
            self.pdu_dispatcher.send_game_over(
                client,
                winner_id,
                losing_client.pid,
                reason
            )
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
            sockets = [client.sock for client in self.clients]
            readable, _, _ = select.select(sockets, [], [], 0.5)

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
                    self.return_to_lobby(client)
                    return
