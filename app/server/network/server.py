import socket
from game.session import GameSession
from core.player import Player

class Server:
    def __init__(self, host="0.0.0.0", port=6767, max_clients=2):
        self.host = host
        self.port = port

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind((self.host, self.port))
        self.sock.listen(max_clients)

        self.session = GameSession(max_clients)
        self.next_id = 0

        print(f"Server running on {self.host}:{self.port}")


    def start(self):
        print("Waiting for 2 players...")

        while not self.session.is_full():
            conn, addr = self.sock.accept()

            print(f"Player connected on {addr[0]}:{addr[1]}")

            player = Player(self.next_id, conn)
            self.next_id += 1

            player.send("Waiting for opponent...")

            self.session.add_player(player)

        print("Lobby full. Starting game...")
        self.session.start()
        self.session.run()

    def stop(self):
        self.sock.close()
