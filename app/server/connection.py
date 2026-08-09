import socket
from app.server.connected_client import ConnectedClient
from app.server.pdu_dispatcher import PduDispatcher
from app.server.game_state import StateBuilder 
from app.shared.protocol import encode_pdu, decode_pdu

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
                    continue

                accepted = self.pdu_dispatcher.handle_player_ready(
                    client, 
                    pdu
                )
                if accepted:
                    state = self.state_builder.build_lobby_state()
                    self.pdu_dispatcher.send_game_state_update(client, state)
                    break
                ### everything in between diess!!
        print("Lobby full!")

    def start(self):
        self.sock.bind((self.host, self.port))
        self.sock.listen(self.max_clients)

        print(f"Server listening on {self.host}:{self.port}")
        print(f"Waiting for {self.max_clients} players...")
