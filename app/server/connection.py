import socket
from app.server.connected_client import ConnectedClient 
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

            try: 
                pdu = decode_pdu(client_sock)
            except ConnectionError:
                client_sock.close()
                continue

            if pdu.get("type") != "PLAYER_READY":
                client_sock.sendall(
                    encode_pdu({
                        "type": "ERROR",
                        "seq_num": self.seq_num,
                        "reason": "fawk u how did u even do that"
                    })
                )
                client_sock.close()
                continue

            username = pdu.get("username")
            if not username or username == "":
                client_sock.sendall(
                    encode_pdu({
                        "type": "ERROR",
                        "seq_num": self.seq_num,
                        "reason": "shit is empty"   
                    })
                )
                client_sock.close()
                continue

            #create valid player instance
            player = ConnectedClient(
                client_sock,
                address,
                username
            )
            player.pid = len(self.clients) + 1
            self.clients.append(player)

            self.seq_num = pdu.get("seq_num") + 1
            player.send({
                "type": "GAME_STATE_UPDATE",
                "seq_num": self.seq_num,
                "phase": "LOBBY"
            })

            print(f"{username} accepted. ({len(self.clients)}/{self.max_clients})")

        print("Lobby full!")

    def start(self):
        self.sock.bind((self.host, self.port))
        self.sock.listen(self.max_clients)

        print(f"Server listening on {self.host}:{self.port}")
        print(f"Waiting for {self.max_clients} players...")
