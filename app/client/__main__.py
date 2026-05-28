import socket

HOST = '0.0.0.0'
PORT = 8080

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((HOST, PORT))

def main():
    client.send(b'I am CLIENT\n')
    from_server = client.recv(4096)
    client.close()
    print(from_server.decode()) 

if __name__ == '__main__':
    main()
