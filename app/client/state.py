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

        #seq_num
        self.latest_seq_num = 0
        self.priority_seq_num = None
        self.phase_seq_num = None
        self.trigger_seq_num = None
        self.heartbeat_seq_num = 1

        #server prompts and results
        self.pending_request = None
        self.last_stack_resolution = None
        self.last_combat_damage_result = None
        self.last_error = None
        self.last_pong_timestamp = None
        self.is_game_over = False
        self.game_over_info = None
