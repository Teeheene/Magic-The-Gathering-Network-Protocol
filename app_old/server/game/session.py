"""Authoritative MTGNP game lifecycle and PDU dispatcher."""

from __future__ import annotations

import queue
import random
import threading
from typing import Any, Dict, List, Optional, Tuple

from app.server.core.player import Player
from app.server.game.combat import CombatManager, CombatOrchestrator
from app.server.game.effects import discard_cards
from app.server.game.events import EventBus, GameEvent
from app.server.game.game_state import GameState
from app.server.game.gameplay_handler import GameplayHandler
from app.server.game.priority import PriorityManager
from app.server.game.sba import StateBasedActions
from app.server.game.stack import GameStack
from app.server.game.triggers import TriggerManager
from app.shared.cards import validate_deck


class GameSession:
    """Own one game while leaving connection ownership to the lobby server."""

    PRIORITY_ACTIONS = {"PRIORITY_PASS", "PLAY_LAND", "CAST_SPELL", "ACTIVATE_ABILITY"}
    PHASE_ACTIONS = {"DECLARE_ATTACKERS", "DECLARE_BLOCKERS", "ASSIGN_DAMAGE_ORDER"}
    KNOWN_CLIENT_PDUS = PRIORITY_ACTIONS | PHASE_ACTIONS | {
        "MULLIGAN_CHOICE", "DISCARD", "CONCEDE", "TRIGGER_ORDER_RESPONSE",
        "TRIGGER_CHOICE_RESPONSE", "PING", "PLAYER_READY",
    }

    def __init__(
        self,
        max_players: int = 2,
        players: Optional[List[Player]] = None,
        rng: Optional[random.Random] = None,
        priority_time_limit_ms: int = 60000,
    ) -> None:
        self.players: List[Player] = list(players or [])
        self.max_players = max_players
        self.rng = rng or random.Random()
        self.priority_time_limit_ms = priority_time_limit_ms
        self.game_state: Optional[GameState] = None
        self.seq_num = 0
        self.state_seq_nums: Dict[str, int] = {}
        self.last_sent_seq_nums: Dict[str, int] = {}
        self.current_phase_seq_num = 0
        self.running = False
        self.mulligan_counts: Dict[str, int] = {}
        self.mulligan_kept: Dict[str, bool] = {}
        self.pending_damage_orders: set[str] = set()
        self._waiting_for_trigger_decisions = False
        self._priority_after_triggers: Optional[str] = None
        self.game_over_pdu: Optional[Dict[str, Any]] = None

        self.event_bus: Optional[EventBus] = None
        self.stack: Optional[GameStack] = None
        self.priority_manager: Optional[PriorityManager] = None
        self.gameplay_handler: Optional[GameplayHandler] = None
        self.combat_manager: Optional[CombatManager] = None
        self.combat_orchestrator: Optional[CombatOrchestrator] = None
        self.trigger_manager: Optional[TriggerManager] = None

        # Kept for direct/session-level use in tests. The production server owns
        # persistent readers so they survive the GAME_OVER -> LOBBY transition.
        self._inbound: queue.Queue = queue.Queue()

    @property
    def last_state_seq_num(self) -> int:
        """Compatibility accessor for callers that used the old shared token."""
        return max(self.state_seq_nums.values(), default=0)

    def add_player(self, player: Player, player_id: str, deck_list: List[str]) -> Tuple[bool, str]:
        if not isinstance(player_id, str) or not player_id.strip():
            return False, "Player ID cannot be empty."
        player_id = player_id.strip()
        if self.is_full():
            return False, "The session is already full."
        if any(p.player_id and p.player_id.casefold() == player_id.casefold() for p in self.players):
            return False, f"Player ID '{player_id}' is already in use."
        valid, message = validate_deck(deck_list)
        if not valid:
            return False, message
        player.player_id = player_id
        player.deck_list = list(deck_list)
        self.players.append(player)
        return True, "Player joined."

    def is_full(self) -> bool:
        return len(self.players) == self.max_players and all(p.player_id for p in self.players)

    def start(self) -> None:
        """Shuffle, draw opening hands, and enter the London mulligan state."""
        if not self.is_full():
            raise RuntimeError("Cannot start a game before exactly two players are ready.")

        player_ids = [p.player_id for p in self.players if p.player_id]
        self.game_state = GameState(player_ids)
        self.game_state.active_player = self.rng.choice(player_ids)
        self.game_state.phase = "MULLIGAN"
        self.game_state.turn = 0
        self.mulligan_counts = {pid: 0 for pid in player_ids}
        self.mulligan_kept = {pid: False for pid in player_ids}

        for player in self.players:
            library = list(player.deck_list)
            self.rng.shuffle(library)
            self.game_state.libraries[player.player_id] = library
            self._draw_cards(player.player_id, 7, lose_on_empty=False)

        self._initialize_managers()
        self.running = True
        self.broadcast_state()

    def _initialize_managers(self) -> None:
        if not self.game_state:
            raise RuntimeError("Game state must exist before managers are initialized.")
        self.event_bus = EventBus()
        self.stack = GameStack(self.game_state, transport=self, seq_num_provider=self)
        self.priority_manager = PriorityManager(
            self.game_state, self.stack, phase_manager=self, transport=self,
            seq_num_provider=self, time_limit_ms=self.priority_time_limit_ms,
        )
        self.priority_manager.on_empty_stack_passes = self.advance_phase
        self.priority_manager.on_post_resolution = self._after_stack_resolution
        self.gameplay_handler = GameplayHandler(
            self.game_state, self.stack, self.priority_manager,
            phase_manager=self, event_bus=self.event_bus,
        )
        self.combat_manager = CombatManager(self.game_state, transport=self, seq_num_provider=self)
        self.combat_orchestrator = CombatOrchestrator(
            self.combat_manager, self.game_state, event_bus=self.event_bus,
            transport=self, seq_num_provider=self,
        )
        self.trigger_manager = TriggerManager(
            self.game_state, self.stack, transport=self,
            seq_num_provider=self, event_bus=self.event_bus,
        )
        self.trigger_manager.on_decisions_complete = self._resume_after_trigger_decisions

    def run(self) -> None:
        """Standalone receive loop; the network server normally dispatches PDUs."""
        if not self.game_state:
            raise RuntimeError("Call start() before run().")
        for player in self.players:
            threading.Thread(target=self._read_player_loop, args=(player,), daemon=True).start()
        while self.running:
            player, pdu, error = self._inbound.get()
            if error or pdu is None:
                self.handle_disconnect(player)
                break
            self.handle_pdu(player, pdu)

    def _read_player_loop(self, player: Player) -> None:
        while self.running:
            try:
                pdu = player.receive()
                self._inbound.put((player, pdu, None))
                if pdu is None:
                    return
            except Exception as exc:
                self._inbound.put((player, None, exc))
                return

    def handle_pdu(self, player: Player, pdu: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and atomically apply one client PDU."""
        if not self.game_state or not self.running:
            return self._send_error(player, "ILLEGAL_ACTION", "No game is currently running.", pdu)
        if not isinstance(pdu, dict) or not isinstance(pdu.get("type"), str):
            return self._send_error(player, "INVALID_JSON", "PDU must be a JSON object with a type.", pdu)
        pdu_type = pdu["type"]
        if pdu_type not in self.KNOWN_CLIENT_PDUS:
            return self._send_error(player, "UNKNOWN_TYPE", f"Unknown PDU type '{pdu_type}'.", pdu)
        if pdu_type in {"PING", "PLAYER_READY"}:
            return self._send_error(player, "ILLEGAL_ACTION", f"{pdu_type} is handled in the lobby/transport layer.", pdu)

        player_id = player.player_id or ""
        sequence_error = self._validate_sequence(player_id, pdu_type, pdu.get("seq_num"))
        if sequence_error:
            return self._send_error(player, "STALE_ACTION", sequence_error, pdu)

        if pdu_type == "CONCEDE":
            if pdu.get("player_id") != player_id:
                return self._send_error(player, "ILLEGAL_ACTION", "A player may only concede for itself.", pdu)
            return self._finish_game(self.game_state.get_opponent(player_id), player_id, "CONCEDE")

        try:
            result = self._dispatch_action(player_id, pdu_type, pdu)
        except (KeyError, TypeError, ValueError) as exc:
            return self._send_error(player, "ILLEGAL_ACTION", str(exc), pdu)

        if result.get("status") == "ERROR":
            return self._send_error(
                player, result.get("code", "ILLEGAL_ACTION"),
                result.get("message", "The action is not legal."), pdu,
            )
        if result.get("status") == "GAME_OVER":
            return result.get("pdu") or self.game_over_pdu or result

        if self.running and pdu_type not in {"MULLIGAN_CHOICE", "DISCARD"}:
            if pdu_type in {"PLAY_LAND", "CAST_SPELL", "ACTIVATE_ABILITY"}:
                self._priority_after_triggers = player_id
            game_over = self._apply_state_based_actions()
            if game_over:
                return game_over
            self.broadcast_state()
            if pdu_type in {"PLAY_LAND", "CAST_SPELL", "ACTIVATE_ABILITY"} and not self._waiting_for_trigger_decisions:
                self._priority_after_triggers = None
                self.priority_manager.handle_action(player_id)
        return result

    def _dispatch_action(self, player_id: str, pdu_type: str, pdu: Dict[str, Any]) -> Dict[str, Any]:
        if pdu_type == "MULLIGAN_CHOICE":
            return self._handle_mulligan_choice(player_id, pdu)
        if pdu_type == "DISCARD":
            return self._handle_discard(player_id, self._require_list(pdu, "card_ids"))

        if self.game_state.phase == "MULLIGAN":
            return {"status": "ERROR", "code": "WRONG_PHASE", "message": "Both players must finish mulligans first."}
        if pdu_type == "PRIORITY_PASS":
            return self.priority_manager.handle_pass(player_id)
        if pdu_type == "PLAY_LAND":
            return self.gameplay_handler.play_land(player_id, self._require_str(pdu, "card_id"))
        if pdu_type == "CAST_SPELL":
            return self.gameplay_handler.cast_spell(
                player_id, self._require_str(pdu, "card_id"),
                self._require_list(pdu, "targets"), self._require_dict(pdu, "mana_payment"),
            )
        if pdu_type == "ACTIVATE_ABILITY":
            return self.gameplay_handler.activate_ability(
                player_id, self._require_str(pdu, "source_id"), self._require_int(pdu, "ability_index"),
                self._require_list(pdu, "targets"), self._require_dict(pdu, "cost_payment"),
            )
        if pdu_type == "DECLARE_ATTACKERS":
            return self._declare_attackers(player_id, self._require_list(pdu, "attackers"))
        if pdu_type == "DECLARE_BLOCKERS":
            return self._declare_blockers(player_id, self._require_list(pdu, "blockers"))
        if pdu_type == "ASSIGN_DAMAGE_ORDER":
            return self._assign_damage_order(
                player_id, self._require_str(pdu, "attacker_id"), self._require_list(pdu, "blocker_order"),
            )
        if pdu_type == "TRIGGER_ORDER_RESPONSE":
            accepted = self.trigger_manager.handle_trigger_order_response(
                player_id, self._require_list(pdu, "ordered_trigger_ids")
            )
            if not accepted:
                return {"status": "ERROR", "code": "TRIGGER_ORDER_INVALID", "message": "Invalid trigger order."}
            return {"status": "SUCCESS"}
        if pdu_type == "TRIGGER_CHOICE_RESPONSE":
            accepted = self.trigger_manager.handle_trigger_choice_response(
                player_id, self._require_str(pdu, "trigger_id"),
                self._require_bool(pdu, "accept"), pdu.get("chosen_target"),
            )
            if not accepted:
                return {"status": "ERROR", "code": "TRIGGER_CHOICE_INVALID", "message": "Invalid trigger choice."}
            return {"status": "SUCCESS"}
        return {"status": "ERROR", "code": "UNKNOWN_TYPE", "message": f"Unknown PDU type '{pdu_type}'."}

    def _handle_mulligan_choice(self, player_id: str, pdu: Dict[str, Any]) -> Dict[str, Any]:
        if self.game_state.phase != "MULLIGAN" or self.mulligan_kept.get(player_id):
            return {"status": "ERROR", "code": "WRONG_PHASE", "message": "Mulligan choices are not currently accepted."}
        keep = self._require_bool(pdu, "keep")
        cards = self._require_list(pdu, "cards_to_bottom")
        if not all(isinstance(card, str) for card in cards):
            raise ValueError("cards_to_bottom must contain card IDs.")

        if not keep:
            if cards:
                return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Do not bottom cards until keeping."}
            self.game_state.libraries[player_id].extend(self.game_state.hands[player_id])
            self.game_state.hands[player_id].clear()
            self.rng.shuffle(self.game_state.libraries[player_id])
            self.mulligan_counts[player_id] += 1
            self._draw_cards(player_id, 7, lose_on_empty=False)
            self.send_state_to_player(player_id)
            return {"status": "SUCCESS", "action": "MULLIGAN_CHOICE", "kept": False}

        expected = self.mulligan_counts[player_id]
        if len(cards) != expected or len(set(cards)) != len(cards):
            return {
                "status": "ERROR", "code": "ILLEGAL_ACTION",
                "message": f"You must put exactly {expected} distinct card(s) on the bottom.",
            }
        hand_copy = list(self.game_state.hands[player_id])
        if any(card not in hand_copy for card in cards):
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "A selected card is not in your hand."}
        for card in cards:
            self.game_state.hands[player_id].remove(card)
            self.game_state.libraries[player_id].append(card)
        self.mulligan_kept[player_id] = True
        self.send_state_to_player(player_id)
        if all(self.mulligan_kept.values()):
            self._begin_first_turn()
        return {"status": "SUCCESS", "action": "MULLIGAN_CHOICE", "kept": True}

    def _begin_first_turn(self) -> None:
        self.game_state.turn = 1
        self._enter_untap_step("MULLIGAN")

    def _declare_attackers(self, player_id: str, attackers: List[Any]) -> Dict[str, Any]:
        if self.game_state.phase != "DECLARE_ATTACKERS" or self.game_state.priority_holder is not None:
            return {"status": "ERROR", "code": "WRONG_PHASE", "message": "It is not the Declare Attackers Step."}
        accepted, message = self.combat_manager.validate_and_declare_attackers(player_id, attackers, self.event_bus)
        if not accepted:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": message}
        triggers_ready = self._place_pending_triggers()
        self.broadcast_state()
        if not attackers:
            self._transition_to("END_OF_COMBAT", grant_priority=True)
        elif triggers_ready:
            self._priority_after_triggers = None
            self.priority_manager.open_priority_window()
        return {"status": "SUCCESS", "action": "DECLARE_ATTACKERS"}

    def _declare_blockers(self, player_id: str, blockers: List[Any]) -> Dict[str, Any]:
        if self.game_state.phase != "DECLARE_BLOCKERS" or self.game_state.priority_holder is not None:
            return {"status": "ERROR", "code": "WRONG_PHASE", "message": "It is not the Declare Blockers Step."}
        accepted, message = self.combat_manager.validate_and_declare_blockers(player_id, blockers)
        if not accepted:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": message}
        self.broadcast_state()
        self.priority_manager.open_priority_window()
        return {"status": "SUCCESS", "action": "DECLARE_BLOCKERS"}

    def _assign_damage_order(self, player_id: str, attacker_id: str, blocker_order: List[Any]) -> Dict[str, Any]:
        if self.game_state.phase != "ASSIGN_DAMAGE_ORDER":
            return {"status": "ERROR", "code": "WRONG_PHASE", "message": "Damage order is not currently being assigned."}
        if player_id != self.game_state.active_player or attacker_id not in self.pending_damage_orders:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "This damage order was not requested."}
        accepted, message = self.combat_manager.set_damage_order(attacker_id, blocker_order)
        if not accepted:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": message}
        self.pending_damage_orders.remove(attacker_id)
        if not self.pending_damage_orders:
            self.priority_manager.open_priority_window()
        return {"status": "SUCCESS", "action": "ASSIGN_DAMAGE_ORDER"}

    def _handle_discard(self, player_id: str, card_ids: List[Any]) -> Dict[str, Any]:
        if self.game_state.phase != "CLEANUP" or player_id != self.game_state.active_player:
            return {"status": "ERROR", "code": "WRONG_PHASE", "message": "Discard is only accepted from the active player at Cleanup."}
        if len(self.game_state.hands[player_id]) <= 7:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "No cleanup discard is required."}
        if not card_ids or len(set(card_ids)) != len(card_ids) or any(card not in self.game_state.hands[player_id] for card in card_ids):
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Every discarded card must be a distinct card in your hand."}
        discard_cards(player_id, card_ids, self.game_state)
        if len(self.game_state.hands[player_id]) > 7:
            self.send_state_to_player(player_id)
        else:
            self._complete_cleanup()
        return {"status": "SUCCESS", "action": "DISCARD"}

    def _validate_sequence(self, player_id: str, pdu_type: str, received: Any) -> Optional[str]:
        if not isinstance(received, int) or isinstance(received, bool):
            return "PDU requires an integer seq_num."
        if pdu_type == "CONCEDE":
            expected = self.last_sent_seq_nums.get(player_id)
            if expected is not None and received != expected:
                return f"Sequence number mismatch: expected {expected}, received {received}."
            return None
        expected: Optional[int] = None
        if pdu_type in self.PRIORITY_ACTIONS:
            if self.game_state.priority_holder != player_id:
                # Priority ownership has a more useful dedicated error than a
                # token mismatch, but only after confirming a token exists.
                return None
            expected = self.priority_manager.current_priority_seq_num
        elif pdu_type in self.PHASE_ACTIONS:
            expected = self.current_phase_seq_num
        elif pdu_type in {"DISCARD", "MULLIGAN_CHOICE"}:
            expected = self.state_seq_nums.get(player_id)
        elif pdu_type in {"TRIGGER_ORDER_RESPONSE", "TRIGGER_CHOICE_RESPONSE"}:
            expected = getattr(self.trigger_manager, "current_request_seq_num", 0)
        if expected is not None and received != expected:
            return f"Sequence number mismatch: expected {expected}, received {received}."
        return None

    def _apply_state_based_actions(self) -> Optional[Dict[str, Any]]:
        _, events, game_over = StateBasedActions.check_and_apply(self.game_state)
        if game_over:
            return self._finish_game(game_over["winner_id"], game_over["loser_id"], game_over["reason"])
        for event in events:
            self.event_bus.publish(event)
        self._place_pending_triggers()
        return None

    def _after_stack_resolution(self) -> bool:
        if not self.running:
            return False
        self._priority_after_triggers = self.game_state.active_player
        game_over = self._apply_state_based_actions()
        if not game_over:
            self.broadcast_state()
        ready = self.running and not self._waiting_for_trigger_decisions
        if ready:
            self._priority_after_triggers = None
        return ready

    def _place_pending_triggers(self) -> bool:
        if self.trigger_manager:
            active = self.game_state.active_player
            ready = self.trigger_manager.place_pending_triggers_on_stack(active, self.game_state.get_opponent(active))
            self._waiting_for_trigger_decisions = not ready
            if not ready:
                self.game_state.priority_holder = None
                if self.priority_manager:
                    self.priority_manager.deadline = None
            return ready
        return True

    def _resume_after_trigger_decisions(self) -> None:
        if not self.running or not self._waiting_for_trigger_decisions:
            return
        self._waiting_for_trigger_decisions = False
        self.broadcast_state()
        recipient = self._priority_after_triggers or self.game_state.active_player
        self._priority_after_triggers = None
        self.priority_manager.grant_priority(recipient)

    def _finish_game(self, winner_id: str, loser_id: str, reason: str) -> Dict[str, Any]:
        pdu = {
            "type": "GAME_OVER", "seq_num": self.next_seq_num(),
            "winner_id": winner_id, "loser_id": loser_id, "reason": reason,
        }
        self.broadcast(pdu)
        self.game_over_pdu = pdu
        self.running = False
        if self.game_state:
            self.game_state.priority_holder = None
        return pdu

    def handle_disconnect(self, player: Player) -> Optional[Dict[str, Any]]:
        if not self.running or not self.game_state:
            return None
        loser = player.player_id or ""
        return self._finish_game(self.game_state.get_opponent(loser), loser, "DISCONNECT")

    def handle_priority_timeout(self) -> Optional[Dict[str, Any]]:
        if not self.running or not self.game_state or not self.game_state.priority_holder:
            return None
        loser = self.game_state.priority_holder
        return self._finish_game(self.game_state.get_opponent(loser), loser, "DISCONNECT")

    def seconds_until_priority_timeout(self) -> Optional[float]:
        return self.priority_manager.seconds_until_timeout() if self.priority_manager else None

    def _send_error(self, player: Player, code: str, message: str, rejected: Any = None) -> Dict[str, Any]:
        rejected_action = rejected if isinstance(rejected, dict) else {}
        rejected_seq = rejected_action.get("seq_num")
        seq = rejected_seq if isinstance(rejected_seq, int) else self.next_seq_num()
        pdu = {
            "type": "ERROR", "seq_num": seq, "code": code,
            "message": message, "rejected_action": rejected_action,
        }
        try:
            player.send(pdu)
            if player.player_id:
                self.last_sent_seq_nums[player.player_id] = seq
            if (
                self.priority_manager and self.game_state
                and self.game_state.priority_holder == player.player_id
                and self.priority_manager.current_priority_seq_num
            ):
                player.send({
                    "type": "PRIORITY_GRANT",
                    "player_id": player.player_id,
                    "seq_num": self.priority_manager.current_priority_seq_num,
                    "time_limit_ms": self.priority_manager.time_limit_ms,
                })
                self.last_sent_seq_nums[player.player_id] = self.priority_manager.current_priority_seq_num
        except Exception:
            pass
        return pdu

    def send_state_to_player(self, player_id: str) -> Optional[Dict[str, Any]]:
        player = self._player_by_id(player_id)
        if not player or not self.game_state:
            return None
        seq = self.next_seq_num()
        self.state_seq_nums[player_id] = seq
        state = self.game_state.get_personalized_state(player_id)
        if self.combat_manager:
            state["combat"] = {
                "attackers": list(self.combat_manager.attackers),
                "blockers": list(self.combat_manager.blockers),
                "damage_orders": dict(self.combat_manager.damage_orders),
                "needs_damage_order": sorted(self.pending_damage_orders),
            }
        if self.game_state.phase == "MULLIGAN":
            state["mulligans_taken"] = self.mulligan_counts.get(player_id, 0)
            state["mulligan_kept"] = self.mulligan_kept.get(player_id, False)
        pdu = {"type": "GAME_STATE_UPDATE", "seq_num": seq, "state": state}
        player.send(pdu)
        self.last_sent_seq_nums[player_id] = seq
        return pdu

    def broadcast_state(self) -> None:
        for player in self.players:
            if player.player_id:
                try:
                    self.send_state_to_player(player.player_id)
                except Exception:
                    pass

    def send_to_player(self, player_id: str, pdu: Dict[str, Any]) -> None:
        player = self._player_by_id(player_id)
        if player:
            player.send(pdu)
            seq = pdu.get("seq_num")
            if isinstance(seq, int):
                self.last_sent_seq_nums[player_id] = seq

    def broadcast(self, pdu: Dict[str, Any]) -> None:
        for player in self.players:
            try:
                player.send(dict(pdu))
                seq = pdu.get("seq_num")
                if player.player_id and isinstance(seq, int):
                    self.last_sent_seq_nums[player.player_id] = seq
            except Exception:
                pass

    def next_seq_num(self) -> int:
        self.seq_num += 1
        return self.seq_num

    def get_current_phase(self) -> str:
        return self.game_state.phase if self.game_state else "LOBBY"

    def get_active_player(self) -> str:
        return self.game_state.active_player if self.game_state else ""

    def is_main_phase(self) -> bool:
        return self.get_current_phase() in ("PRECOMBAT_MAIN", "POSTCOMBAT_MAIN")

    def get_turn_number(self) -> int:
        return self.game_state.turn if self.game_state else 0

    def has_land_been_played(self) -> bool:
        return bool(self.game_state and self.game_state.land_played_this_turn)

    def mark_land_played(self) -> None:
        if self.game_state:
            self.game_state.land_played_this_turn = True

    def is_first_turn_first_player(self) -> bool:
        return bool(self.game_state and self.game_state.turn == 1)

    def advance_phase(self) -> None:
        if not self.running or not self.game_state:
            return
        phase = self.game_state.phase
        if phase == "UPKEEP":
            self._transition_to("DRAW", grant_priority=False)
            if not (self.game_state.turn == 1):
                if not self._draw_cards(self.game_state.active_player, 1, lose_on_empty=True):
                    return
                self.event_bus.publish(GameEvent("card_drawn", {"player_id": self.game_state.active_player}))
            self._apply_state_based_actions()
            if self.running:
                self.broadcast_state()
                if not self._waiting_for_trigger_decisions:
                    self._priority_after_triggers = None
                    self.priority_manager.open_priority_window()
        elif phase == "DRAW":
            self._transition_to("PRECOMBAT_MAIN", grant_priority=True)
        elif phase == "PRECOMBAT_MAIN":
            self._transition_to("BEGIN_COMBAT", grant_priority=True)
        elif phase == "BEGIN_COMBAT":
            self._transition_to("DECLARE_ATTACKERS", grant_priority=False)
        elif phase == "DECLARE_ATTACKERS":
            self._transition_to("DECLARE_BLOCKERS", grant_priority=False)
        elif phase == "DECLARE_BLOCKERS":
            needed = set(self.combat_manager.needs_damage_order())
            if needed:
                self.pending_damage_orders = needed
                self._transition_to("ASSIGN_DAMAGE_ORDER", grant_priority=False)
            else:
                self._begin_combat_damage()
        elif phase == "ASSIGN_DAMAGE_ORDER":
            self._begin_combat_damage()
        elif phase == "FIRST_STRIKE_DAMAGE":
            self._resolve_regular_combat_damage()
        elif phase == "COMBAT_DAMAGE":
            self._transition_to("END_OF_COMBAT", grant_priority=True)
        elif phase == "END_OF_COMBAT":
            self.combat_manager.reset_combat()
            self.pending_damage_orders.clear()
            for permanents in self.game_state.battlefield.values():
                for permanent in permanents:
                    permanent["damage"] = 0
            self._transition_to("POSTCOMBAT_MAIN", grant_priority=True)
        elif phase == "POSTCOMBAT_MAIN":
            self._transition_to("END_STEP", grant_priority=True)
        elif phase == "END_STEP":
            self._transition_to("CLEANUP", grant_priority=False)
            if len(self.game_state.hands[self.game_state.active_player]) > 7:
                self.send_state_to_player(self.game_state.active_player)
            else:
                self._complete_cleanup()

    def _begin_combat_damage(self) -> None:
        if self.combat_manager.has_first_strike_or_double_strike():
            self._transition_to("FIRST_STRIKE_DAMAGE", grant_priority=False)
            result = self.combat_orchestrator.execute_combat_damage_step(is_first_strike_step=True)
            if self._handle_combat_game_over(result):
                return
            triggers_ready = self._place_pending_triggers()
            self.broadcast_state()
            if triggers_ready:
                self._priority_after_triggers = None
                self.priority_manager.open_priority_window()
        else:
            self._resolve_regular_combat_damage()

    def _resolve_regular_combat_damage(self) -> None:
        self._transition_to("COMBAT_DAMAGE", grant_priority=False)
        result = self.combat_orchestrator.execute_combat_damage_step(is_first_strike_step=False)
        if self._handle_combat_game_over(result):
            return
        triggers_ready = self._place_pending_triggers()
        self.broadcast_state()
        if triggers_ready:
            self._transition_to("END_OF_COMBAT", grant_priority=True)

    def _handle_combat_game_over(self, result: Dict[str, Any]) -> bool:
        game_over = result.get("game_over_result")
        if not game_over:
            return False
        self._finish_game(game_over["winner_id"], game_over["loser_id"], game_over["reason"])
        return True

    def _transition_to(self, phase: str, grant_priority: bool) -> None:
        previous = self.game_state.phase
        for pool in self.game_state.mana_pools.values():
            for color in pool:
                pool[color] = 0
        self.game_state.phase = phase
        self.game_state.priority_holder = None
        self.current_phase_seq_num = self.next_seq_num()
        self.broadcast({
            "type": "PHASE_TRANSITION", "seq_num": self.current_phase_seq_num,
            "from_phase": previous, "to_phase": phase,
            "active_player": self.game_state.active_player, "turn": self.game_state.turn,
        })
        self.event_bus.publish(GameEvent("phase_began", {"phase": phase, "active_player": self.game_state.active_player}))
        self._priority_after_triggers = self.game_state.active_player
        triggers_ready = self._place_pending_triggers()
        if grant_priority and self.running and triggers_ready:
            self._priority_after_triggers = None
            self.priority_manager.open_priority_window()

    def _enter_untap_step(self, previous: str) -> None:
        self._transition_to("UNTAP", grant_priority=False)
        active = self.game_state.active_player
        self.game_state.land_played_this_turn = False
        for permanent in self.game_state.battlefield[active]:
            permanent["tapped"] = False
            if "summoning_sick" in permanent:
                permanent["summoning_sick"] = False
        self.broadcast_state()
        self._transition_to("UPKEEP", grant_priority=True)

    def _complete_cleanup(self) -> None:
        for effect in reversed(self.game_state.temporary_effects):
            permanent = self.game_state.get_permanent(effect.get("target", ""))
            if not permanent:
                continue
            if effect.get("type") == "PT_MOD":
                permanent["power"] -= effect.get("power_mod", 0)
                permanent["toughness"] -= effect.get("toughness_mod", 0)
            elif effect.get("type") == "KEYWORD":
                keywords = permanent.get("keywords", [])
                if effect.get("keyword") in keywords:
                    keywords.remove(effect["keyword"])
        for permanents in self.game_state.battlefield.values():
            for permanent in permanents:
                permanent["damage"] = 0
        self.game_state.temporary_effects.clear()
        self.game_state.damage_prevention_shields.clear()
        self.game_state.cant_gain_life = False
        self.game_state.cant_prevent_damage = False
        self.broadcast_state()
        self.game_state.active_player = self.game_state.get_opponent(self.game_state.active_player)
        self.game_state.turn += 1
        self._enter_untap_step("CLEANUP")

    def _draw_cards(self, player_id: str, count: int, lose_on_empty: bool) -> bool:
        for _ in range(count):
            if not self.game_state.libraries[player_id]:
                if lose_on_empty:
                    self._finish_game(self.game_state.get_opponent(player_id), player_id, "DECK_EMPTY")
                    return False
                break
            self.game_state.hands[player_id].append(self.game_state.libraries[player_id].pop(0))
        return True

    def _player_by_id(self, player_id: str) -> Optional[Player]:
        return next((p for p in self.players if p.player_id == player_id), None)

    @staticmethod
    def _require_str(pdu: Dict[str, Any], field: str) -> str:
        value = pdu.get(field)
        if not isinstance(value, str) or not value:
            raise ValueError(f"Field '{field}' must be a non-empty string.")
        return value

    @staticmethod
    def _require_int(pdu: Dict[str, Any], field: str) -> int:
        value = pdu.get(field)
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"Field '{field}' must be an integer.")
        return value

    @staticmethod
    def _require_bool(pdu: Dict[str, Any], field: str) -> bool:
        value = pdu.get(field)
        if not isinstance(value, bool):
            raise ValueError(f"Field '{field}' must be a boolean.")
        return value

    @staticmethod
    def _require_list(pdu: Dict[str, Any], field: str) -> List[Any]:
        value = pdu.get(field)
        if not isinstance(value, list):
            raise ValueError(f"Field '{field}' must be a list.")
        return value

    @staticmethod
    def _require_dict(pdu: Dict[str, Any], field: str) -> Dict[str, Any]:
        value = pdu.get(field)
        if not isinstance(value, dict):
            raise ValueError(f"Field '{field}' must be an object.")
        return value
