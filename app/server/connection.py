import json
import socket
from typing import Optional

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
        self.running = True
        self.clients = []
        self.seq_num = 0

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
        while self.running:
            # Clear ready status for all connected clients upon entering lobby
            for client in list(self.clients):
                client.ready_in_lobby = False

            while self.running:
                # Accept new connections if below max_clients
                if len(self.clients) < self.max_clients:
                    self.sock.settimeout(0.2)
                    try:
                        client_sock, address = self.sock.accept()
                        print(f"Connection attempt from {address}")
                        client = ConnectedClient(
                            sock=client_sock, address=address, verbose=self.verbose
                        )
                        self.clients.append(client)
                    except (socket.timeout, TimeoutError, OSError):
                        pass

                # Check for PLAYER_READY from all connected clients
                for client in list(self.clients):
                    if not getattr(client, "ready_in_lobby", False):
                        client.sock.settimeout(0.05)
                        try:
                            pdu = client.receive()
                            if isinstance(pdu, dict) and pdu.get("type") == "PLAYER_READY":
                                if self.pdu_dispatcher.handle_player_ready(client, pdu):
                                    client.ready_in_lobby = True
                                    state = self.state_builder.build_lobby_state()
                                    for c in self.clients:
                                        self.pdu_dispatcher.send_game_state_update(c, state)
                        except (socket.timeout, TimeoutError, OSError):
                            pass
                        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
                            from app.server.pdu_dispatcher import MSG_INVALID_JSON, ERR_INVALID_JSON
                            self.pdu_dispatcher.send_error(client, MSG_INVALID_JSON, ERR_INVALID_JSON)
                        except ConnectionError:
                            print(f"Client {client.address} disconnected in lobby.")
                            if client in self.clients:
                                self.clients.remove(client)
                            client.close()

                # Check if all clients are connected AND ready
                ready_count = sum(1 for c in self.clients if getattr(c, "ready_in_lobby", False))
                if len(self.clients) == self.max_clients and ready_count == self.max_clients:
                    print("Both players connected and ready! Starting game loop...")
                    self.game.run_game_loop()
                    break

    def refuse_extra_connections(self):
        """Actively reject and close any additional connection attempts beyond max_clients."""
        self.sock.settimeout(0.01)
        try:
            extra_sock, address = self.sock.accept()
            print(f"Refusing 3rd connection from {address}")
            self.seq_num += 1
            err_pdu = {
                "type": "ERROR",
                "seq_num": self.seq_num,
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
        if disconnected_client:
            if disconnected_client in self.clients:
                self.clients.remove(disconnected_client)
            disconnected_client.close()
            print(f"Player {getattr(disconnected_client, 'pid', 'unknown')} disconnected.")

        self.game.reset()
        for client in list(self.clients):
            client.mulligan_taken = 0
            client.mulligan_kept = False
            client.ready_in_lobby = False

        lobby_state = self.state_builder.build_lobby_state()
        for client in list(self.clients):
            try:
                self.pdu_dispatcher.send_game_state_update(client, lobby_state)
            except (ConnectionError, OSError):
                if client in self.clients:
                    self.clients.remove(client)
                client.close()

        print(f"Returned to lobby. Current connected players: {len(self.clients)}")
