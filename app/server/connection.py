import socket

from app.server.connected_client import ConnectedClient
from app.server.game import Game


class ServerConnection:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 4444,
        max_clients: int = 2,
        verbose: bool = False,
    ):
        self.host = host
        self.port = port
        self.max_clients = max_clients
        self.verbose = verbose
        self.clients = []

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.game = Game(self)
        self.pdu_dispatcher = self.game.pdu_dispatcher
        self.state_builder = self.game.state_builder

    def start(self):
        self.sock.bind((self.host, self.port))
        self.sock.listen(self.max_clients)
        print(f"Server listening on {self.host}:{self.port}")
        print(f"Waiting for {self.max_clients} players...")

    def wait_for_players(self):
        while True:
            while len(self.clients) < self.max_clients:
                self.sock.settimeout(0.5)
                try:
                    client_sock, address = self.sock.accept()
                except (socket.timeout, TimeoutError):
                    continue
                print(f"Connection attempt from {address}")
                client = ConnectedClient(
                    sock=client_sock, address=address, verbose=self.verbose
                )

                while True:
                    try:
                        pdu = client.receive()
                    except (ConnectionError, OSError):
                        print(f"{address} disconnected before joining")
                        client.close()
                        break

                    accepted = self.pdu_dispatcher.handle_player_ready(client, pdu)
                    if accepted:
                        self.clients.append(client)
                        state = self.state_builder.build_lobby_state()
                        for joined_client in self.clients:
                            self.pdu_dispatcher.send_game_state_update(
                                joined_client,
                                state,
                            )
                        break

            print("Lobby full!")
            self.game.run_game_loop()

    def refuse_extra_connections(self):
        """Actively reject and close any additional connection attempts beyond max_clients."""
        self.sock.settimeout(0.01)
        try:
            extra_sock, address = self.sock.accept()
            print(f"Refusing 3rd connection from {address}")
            err_pdu = {
                "type": "ERROR",
                "seq_num": self.seq_num + 1,
                "code": "ILLEGAL_ACTION",
                "message": "Lobby full. Server accepts maximum 2 players.",
                "rejected_action": {},
            }
            try:
                from app.shared.protocol import encode_pdu

                extra_sock.sendall(encode_pdu(err_pdu))
            except Exception:
                pass
            extra_sock.close()
        except (socket.timeout, TimeoutError, OSError):
            pass

    def return_to_lobby(self, disconnected_client=None):
        if disconnected_client and disconnected_client in self.clients:
            self.clients.remove(disconnected_client)
            disconnected_client.close()
            print(f"Player {disconnected_client.pid} disconnected.")

        self.game.reset()
        for client in list(self.clients):
            client.mulligan_taken = 0
            client.mulligan_kept = False

        lobby_state = self.state_builder.build_lobby_state()
        for client in list(self.clients):
            try:
                self.pdu_dispatcher.send_game_state_update(client, lobby_state)
            except (ConnectionError, OSError):
                if client in self.clients:
                    self.clients.remove(client)
                client.close()

        print(f"Returned to lobby. Current connected players: {len(self.clients)}")
