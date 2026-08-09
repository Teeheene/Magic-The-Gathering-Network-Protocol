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
            "STACK_RESOLVE": self.handle_stack_resolve,
            "COMBAT_DAMAGE_RESULT": self.handle_combat_damage_result,
            "GAME_OVER": self.handle_game_over,
            "ERROR": self.handle_error,
            "PONG": self.handle_pong,
        }

    def handle(self, pdu):
        pdu_type = pdu.get("type")
        seq_num = pdu.get("seq_num")

        if seq_num is not None:
            self.state.latest_seq_num = seq_num

        handler = self.handlers.get(pdu_type)
        if handler is None:
            raise ValueError(
                f"Unknown PDU type: {pdu_type}"
            )
        handler(pdu)

    #receive pdus
    def handle_game_state_update(self, pdu):
        pass

    def handle_phase_transition(self, pdu):
        pass

    def handle_priority_grant(self, pdu):
        pass

    def handle_stack_push(self, pdu):
        pass

    def handle_trigger_order(self, pdu):
        pass

    def handle_trigger_choice(self, pdu):
        pass

    def handle_stack_resolve(self, pdu):
        pass

    def handle_combat_damage_result(self, pdu):
        pass

    def handle_game_over(self, pdu):
        pass

    def handle_error(self, pdu):
        pass

    def handle_pong(self, pdu):
        pass

    #send pdus
    def send_player_ready(self):
        self.connection.send({
            "type": "PLAYER_READY",
            "seq_num": self.state.latest_seq_num,
            "player_id": self.state.pid,
            "deck_list": self.state.deck_list
        })

    def send_mulligan_choice(self):
        pass

    def send_priority_pass(self):
        pass

    def send_cast_spell(self):
        pass

    def send_activate_ability(self):
        pass

    def send_trigger_order_response(self):
        pass

    def send_trigger_choice_response(self):
        pass

    def send_declare_attackers(self):
        pass

    def send_declare_blockers(self):
        pass

    def send_assign_damage_order(self):
        pass

    def send_play_land(self):
        pass

    def send_discard(self):
        pass

    def send_concede(self):
        pass

    def send_ping(self):
        pass