import socket
from network import server

def main():
    serv = server.Server()
    serv.start()

if __name__ == '__main__':
    main()
