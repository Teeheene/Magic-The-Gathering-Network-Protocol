import socket

class Player:
    def __init__(self, idx, conn):
        self.idx = idx
        self.conn = conn

    def send(self, data):
        self.conn.sendall(data.encode())



