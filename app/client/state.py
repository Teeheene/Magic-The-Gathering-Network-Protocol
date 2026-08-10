class ClientState:
    def __init__(self, pid):
        self.connected = True 
        self.joined = False

        #player
        self.pid = pid 
        self.deck_list = []

        #client memory
        self.current_state = {}

        #state
        self.turn = 0
        self.phase = "LOBBY"
        self.active_player = None
        self.priority_holder = None
        self.life_totals = {}
        self.hand = {}
        self.local_hand = []
        self.hand_counts = {}
        self.library_counts = {}
        self.battlefield = {}
        self.graveyard = {}
        self.stack = []
        self.land_played_this_turn = False
        self.attackers = []
        self.blockers = []
        self.damage_orders = {}
        self.attackers_declared = False
        self.blockers_declared = False
        self.pending_damage_orders = []

        #seq_num
        self.latest_seq_num = 0
        self.last_received_pdu_seq_num = None
        self.player_ready_seq_num = 1
        self.priority_seq_num = None
        self.phase_seq_num = None
        self.trigger_seq_num = None
        self.heartbeat_seq_num = 1


        #server prompts and results
        self.pending_request = None
        self.last_stack_resolution = None
        self.last_combat_damage_result = None
        self.last_pong_timestamp = None
        self.is_game_over = False
        self.game_over_info = None

    def update_game_state(self, state_dict):
        self.current_state = state_dict
        if "turn" in state_dict:
            self.turn = state_dict["turn"]
        if "phase" in state_dict:
            self.phase = state_dict["phase"]
        if "active_player" in state_dict:
            self.active_player = state_dict["active_player"]
        if "priority_holder" in state_dict:
            self.priority_holder = state_dict["priority_holder"]
        if "life_totals" in state_dict:
            self.life_totals = state_dict["life_totals"]
        if "hand" in state_dict:
            self.local_hand = state_dict["hand"]
        if "battlefield" in state_dict:
            self.battlefield = state_dict["battlefield"]
        if "stack" in state_dict:
            self.stack = state_dict["stack"]

    def reset_for_lobby(self):
        self.phase = "LOBBY"
        self.turn = 0
        self.active_player = None
        self.priority_holder = None
        self.life_totals = {}
        self.hand = {}
        self.local_hand = []
        self.hand_counts = {}
        self.library_counts = {}
        self.battlefield = {}
        self.graveyard = {}
        self.stack = []
        self.land_played_this_turn = False
        self.attackers = []
        self.blockers = []
        self.damage_orders = {}
        self.attackers_declared = False
        self.blockers_declared = False
        self.pending_damage_orders = []

        self.priority_seq_num = None
        self.phase_seq_num = None
        self.trigger_seq_num = None

        self.pending_request = None
        self.last_stack_resolution = None
        self.last_combat_damage_result = None
        self.is_game_over = False
        self.game_over_info = None

