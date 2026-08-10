from copy import deepcopy
import time

from app.client.state import ClientState

class PduDispatcher:
    def __init__(self, state: ClientState, connection):
        self.state = state
        self.connection = connection
        self.handlers = {
            "GAME_STATE_UPDATE": self.handle_game_state_update,
            "PHASE_TRANSITION": self.handle_phase_transition,
            "PRIORITY_GRANT": self.handle_priority_grant,
            "STACK_PUSH": self.handle_stack_push,
            "TRIGGER_ORDER": self.handle_trigger_order,
            "TRIGGER_CHOICE": self.handle_trigger_choice,
            "CARD_CHOICE_REQUEST": self.handle_card_choice_request,
            "STACK_RESOLVE": self.handle_stack_resolve,
            "COMBAT_DAMAGE_RESULT": self.handle_combat_damage_result,
            "GAME_OVER": self.handle_game_over,
            "ERROR": self.handle_error,
            "PONG": self.handle_pong,
        }

    def handle(self, pdu):
        pdu_type = pdu.get("type")
        seq_num = pdu.get("seq_num")

        if isinstance(seq_num, int) and not isinstance(seq_num, bool):
            self.state.last_received_pdu_seq_num = seq_num

        if seq_num is not None and pdu_type != "ERROR":
            self.state.latest_seq_num = seq_num

        handler = self.handlers.get(pdu_type)
        if handler is None:
            raise ValueError(
                f"Unknown PDU type: {pdu_type}"
            )
        handler(pdu)
        callback = getattr(self.state, "on_state_change", None)
        if callable(callback):
            callback()

    #receive pdus
    def handle_game_state_update(self, pdu):
        self.state.latest_seq_num = pdu.get("seq_num")
        server_state = pdu.get("state")
        if not isinstance(server_state, dict):
            raise ValueError("GAME_STATE_UPDATE requires a 'state' object.")

        self.state.current_state = deepcopy(server_state)

        #lobby phase deals with no game setup
        if server_state.get("phase") == "LOBBY":
            self.state.reset_for_lobby()
            self.state.joined = False
            return

        remembered_fields = (
            "turn",
            "phase",
            "active_player",
            "priority_holder",
            "life_totals",
            "hand",
            "hand_counts",
            "library_counts",
            "battlefield",
            "graveyard",
            "stack",
            "suspended_cards",
            "land_played_this_turn",
            "attackers",
            "blockers",
            "damage_orders",
            "attackers_declared",
            "blockers_declared",
            "pending_damage_orders",
        )
        for field in remembered_fields:
            if field in server_state:
                setattr(self.state, field, deepcopy(server_state[field]))

        if isinstance(self.state.hand, dict):
            self.state.local_hand = list(self.state.hand.get(self.state.pid, []))
        elif isinstance(self.state.hand, list):
            self.state.local_hand = list(self.state.hand)
        else:
            self.state.local_hand = []

        self.state.joined = True

    def handle_phase_transition(self, pdu):
        self.state.phase_seq_num = pdu["seq_num"]
        self.state.priority_seq_num = None
        self.state.phase = pdu.get("to_phase", self.state.phase)
        self.state.active_player = pdu.get(
            "active_player",
            self.state.active_player
        )
        self.state.turn = pdu.get("turn", self.state.turn)
        self.state.priority_holder = None

    def handle_priority_grant(self, pdu):
        self.state.priority_seq_num = pdu["seq_num"]
        self.state.priority_holder = pdu.get("player_id")

    def handle_stack_push(self, pdu):
        self.state.pending_card_choice = None
        self.state.card_choice_seq_num = None
        stack_item = {
            key: deepcopy(value)
            for key, value in pdu.items()
            if key not in {"type", "seq_num"}
        }
        self.state.stack.append(stack_item)

    def handle_trigger_order(self, pdu):
        self.state.trigger_seq_num = pdu["seq_num"]
        self.state.pending_request = deepcopy(pdu)

    def handle_trigger_choice(self, pdu):
        self.state.trigger_seq_num = pdu["seq_num"]
        self.state.pending_request = deepcopy(pdu)

    def handle_card_choice_request(self, pdu):
        self.state.card_choice_seq_num = pdu["seq_num"]
        self.state.pending_card_choice = deepcopy(pdu)

    def handle_stack_resolve(self, pdu):
        self.state.pending_card_choice = None
        self.state.card_choice_seq_num = None
        stack_item_id = pdu.get("stack_item_id")
        self.state.stack = [
            item for item in self.state.stack
            if item.get("stack_item_id") != stack_item_id
        ]
        self.state.last_stack_resolution = deepcopy(pdu)

    def handle_combat_damage_result(self, pdu):
        self.state.last_combat_damage_result = deepcopy(pdu)
        if isinstance(pdu.get("life_totals"), dict):
            self.state.life_totals = deepcopy(pdu["life_totals"])

    def handle_game_over(self, pdu):
        self.state.is_game_over = True
        self.state.game_over_info = deepcopy(pdu)
        self.state.phase = "GAME_OVER"
        self.state.priority_holder = None
        self.state.priority_seq_num = None

    def handle_error(self, pdu):
        self.state.last_error = deepcopy(pdu)

    def handle_pong(self, pdu):
        seq = pdu.get("seq_num")
        pending = getattr(self.state, "pending_ping_seq", None)
        if pending is not None:
            if seq == pending:
                self.state.last_pong_timestamp = time.time()
                self.state.pending_ping_seq = None
        else:
            self.state.last_pong_timestamp = time.time()

    def send_ping(self, timestamp=None):
        if timestamp is None:
            timestamp = int(time.time() * 1000)

        seq = self.state.heartbeat_seq_num
        self.state.heartbeat_seq_num += 1
        self.state.pending_ping_seq = seq
        self.state.ping_send_time = time.time()

        self.connection.send({
            "type": "PING",
            "seq_num": seq,
            "timestamp": timestamp
        })


    #send pdus
    def send_player_ready(self):
        seq = self.state.player_ready_seq_num
        self.state.player_ready_seq_num += 1
        self.connection.send({
            "type": "PLAYER_READY",
            "seq_num": seq,
            "player_id": self.state.pid,
            "deck_list": self.state.deck_list
        })


    def send_mulligan_choice(self, keep, cards_to_bottom=None):
        self.connection.send({
            "type": "MULLIGAN_CHOICE",
            "seq_num": self.state.latest_seq_num,
            "keep": keep,
            "cards_to_bottom": list(cards_to_bottom or [])
        })

    def send_priority_pass(self):
        self.connection.send({
            "type": "PRIORITY_PASS",
            "seq_num": self._priority_seq_num()
        })

    def send_cast_spell(self, card_id, targets=None, mana_payment=None, mode=None):
        pdu = {
            "type": "CAST_SPELL",
            "seq_num": self._priority_seq_num(),
            "card_id": card_id,
            "targets": list(targets or []),
            "mana_payment": dict(mana_payment or {})
        }
        if mode is not None:
            pdu["mode"] = mode
        self.connection.send(pdu)

    def send_activate_ability(
        self,
        source_id,
        ability_index=0,
        targets=None,
        cost_payment=None
    ):
        self.connection.send({
            "type": "ACTIVATE_ABILITY",
            "seq_num": self._priority_seq_num(),
            "source_id": source_id,
            "ability_index": ability_index,
            "targets": list(targets or []),
            "cost_payment": dict(cost_payment or {})
        })

    def send_trigger_order_response(self, ordered_trigger_ids):
        self.connection.send({
            "type": "TRIGGER_ORDER_RESPONSE",
            "seq_num": self._trigger_seq_num(),
            "ordered_trigger_ids": list(ordered_trigger_ids)
        })
        self.state.pending_request = None

    def send_trigger_choice_response(
        self,
        trigger_id,
        accept,
        chosen_target=None
    ):
        pdu = {
            "type": "TRIGGER_CHOICE_RESPONSE",
            "seq_num": self._trigger_seq_num(),
            "trigger_id": trigger_id,
            "accept": accept
        }
        if chosen_target is not None:
            pdu["chosen_target"] = chosen_target
        self.connection.send(pdu)
        self.state.pending_request = None

    def send_declare_attackers(self, attackers):
        self.connection.send({
            "type": "DECLARE_ATTACKERS",
            "seq_num": self._phase_seq_num(),
            "attackers": list(attackers)
        })

    def send_declare_blockers(self, blockers):
        self.connection.send({
            "type": "DECLARE_BLOCKERS",
            "seq_num": self._phase_seq_num(),
            "blockers": list(blockers)
        })

    def send_assign_damage_order(self, attacker_id, blocker_order):
        self.connection.send({
            "type": "ASSIGN_DAMAGE_ORDER",
            "seq_num": self._phase_seq_num(),
            "attacker_id": attacker_id,
            "blocker_order": list(blocker_order)
        })

    def send_play_land(self, card_id):
        self.connection.send({
            "type": "PLAY_LAND",
            "seq_num": self._priority_seq_num(),
            "card_id": card_id
        })

    def send_discard(self, card_ids):
        self.connection.send({
            "type": "DISCARD",
            "seq_num": self.state.latest_seq_num,
            "card_ids": list(card_ids)
        })

    def send_concede(self):
        self.connection.send({
            "type": "CONCEDE",
            "seq_num": self.state.last_received_pdu_seq_num,
            "player_id": self.state.pid
        })

    def send_card_choice_response(self, **response):
        pdu = {
            "type": "CARD_CHOICE_RESPONSE",
            "seq_num": self.state.card_choice_seq_num,
            "player_id": self.state.pid,
            **response,
        }
        self.connection.send(pdu)

    def send_suspend_card(self, card_id, mana_payment):
        self.connection.send({
            "type": "SUSPEND_CARD",
            "seq_num": self._priority_seq_num(),
            "player_id": self.state.pid,
            "card_id": card_id,
            "mana_payment": dict(mana_payment or {}),
        })

    def _priority_seq_num(self):
        if self.state.priority_seq_num is not None:
            return self.state.priority_seq_num
        return self.state.latest_seq_num

    def _phase_seq_num(self):
        if self.state.phase_seq_num is not None:
            return self.state.phase_seq_num
        return self.state.latest_seq_num

    def _trigger_seq_num(self):
        if self.state.trigger_seq_num is not None:
            return self.state.trigger_seq_num
        return self.state.latest_seq_num
