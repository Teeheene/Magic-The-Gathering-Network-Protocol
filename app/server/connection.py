import socket
import select
from app.server.connected_client import ConnectedClient
from app.server.pdu_dispatcher import PduDispatcher
from app.server.game_state import StateBuilder 

class ServerConnection:
    def __init__(self, 
                 host: str = "0.0.0.0",
                 port: int = 4444,
                 max_clients: int = 2):
        self.host = host
        self.port = port

        self.max_clients = max_clients
        self.clients = []

        self.seq_num = 0
        self.pdu_dispatcher = PduDispatcher(self) 
        self.state_builder = StateBuilder(self)
        self.phase = "LOBBY"

        #setup connection
        self.sock = socket.socket(
            socket.AF_INET, 
            socket.SOCK_STREAM
        )
        self.sock.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1
        )

    def wait_for_players(self):
        while len(self.clients) < self.max_clients:
            client_sock, address = self.sock.accept()
            print(f"Connection attempt from {address}")
            client = ConnectedClient(
                sock=client_sock,
                address=address
            )

            while True:
                try: 
                    pdu = client.receive() 
                except ConnectionError:
                    print(f"{address} disconnected before joining")
                    client.close()
                    break

                accepted = self.pdu_dispatcher.handle_player_ready(
                    client, 
                    pdu
                )
                if accepted:
                    state = self.state_builder.build_lobby_state()
                    for joined_client in self.clients:
                        self.pdu_dispatcher.send_game_state_update(
                            joined_client,
                            state
                        )
                    break
                ### everything in between diess!!
        print("Lobby full!")
        self.run_game_loop()

    def handle_mulligan_phase(self):
        for client in self.clients:
            self.pdu_dispatcher.send_game_state_update(
                client,
                self.state_builder.build_mulligan_state(client)
            )

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
                    client.close()
                    self.clients.remove(client)
                    return False

                self.pdu_dispatcher.handle_mulligan_choice(client, pdu)

        return True

    def handle_untap_phase(self):
        self.turn += 1
        self.phase = "UNTAP"

        #transition phase and build untap_phase
        for client in self.clients:
            self.pdu_dispatcher.send_phase_transition(
                client,
                "MULLIGAN",
                self.phase,
                self.active_player,
                self.turn
            )
            self.pdu_dispatcher.send_game_state_update(
                client,
                self.state_builder.build_untap_state(client)
            )

    def run_game_loop(self):
        """Run mulligans, enter the first turn, then dispatch game actions."""

        if len(self.clients) != self.max_clients:
            raise RuntimeError("The game cannot start until the lobby is full.")

        #phases
        if not self.handle_mulligan_phase():
            return

        self.handle_untap_phase()
        active_player = self.active_player

        self.phase = "UPKEEP"
        for client in self.clients:
            self.pdu_dispatcher.send_phase_transition(
                client,
                "UNTAP",
                self.phase,
                active_player,
                self.turn
            )

        while self.clients:
            sockets = [client.sock for client in self.clients]
            readable, _, _ = select.select(sockets, [], [], 0.5)

            for ready_socket in readable:
                client = next(
                    player
                    for player in self.clients
                    if player.sock is ready_socket
                )
                try:
                    pdu = {}
                    pdu = client.receive()
                    self.pdu_dispatcher.handle(client, pdu)
                except (ConnectionError, OSError):
                    client.close()
                    self.clients.remove(client)

    def start(self):
        self.sock.bind((self.host, self.port))
        self.sock.listen(self.max_clients)

        print(f"Server listening on {self.host}:{self.port}")
        print(f"Waiting for {self.max_clients} players...")
