import socket

from app.server.connected_client import ConnectedClient
from app.server.game import Game


class ServerConnection:
    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 4444,
        max_clients: int = 2,
    ):
        self.host = host
        self.port = port
        self.max_clients = max_clients
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
                client_sock, address = self.sock.accept()
                print(f"Connection attempt from {address}")
                client = ConnectedClient(sock=client_sock, address=address)

                while True:
                    try:
                        pdu = client.receive()
                    except (ConnectionError, OSError):
                        print(f"{address} disconnected before joining")
                        client.close()
                        break

                    accepted = self.pdu_dispatcher.handle_player_ready(client, pdu)
                    if accepted:
                        state = self.state_builder.build_lobby_state()
                        for joined_client in self.clients:
                            self.pdu_dispatcher.send_game_state_update(
                                joined_client,
                                state,
                            )
                        break

            print("Lobby full!")
            self.game.run_game_loop()

    def return_to_lobby(self, disconnected_client):
        if disconnected_client in self.clients:
            self.clients.remove(disconnected_client)
        disconnected_client.close()

        self.game.reset()
        remaining_clients = list(self.clients)
        if remaining_clients:
            lobby_state = self.state_builder.build_lobby_state()
            for client in remaining_clients:
                try:
                    self.pdu_dispatcher.send_game_state_update(client, lobby_state)
                except (ConnectionError, OSError):
                    pass

        for client in remaining_clients:
            client.close()
        self.clients.clear()
        print("A player disconnected. Returning to lobby.")
