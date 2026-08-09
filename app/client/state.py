class ClientState:
    def __init__(self, pid):
        self.connected = True 
        self.joined = False

        #player
        self.pid = pid 
        self.deck_list = []

        #seq_num
        self.latest_seq_num = 0
        self.priority_seq_num = None
        self.heartbeat_seq_num = 1

        self.phase = "LOBBY"
    