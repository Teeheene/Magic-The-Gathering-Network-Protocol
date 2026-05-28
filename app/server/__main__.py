import socket

HOST = '0.0.0.0'
PORT = 4444

serv = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 

serv.bind((HOST, PORT))
serv.listen(5)

def main():
    conn, addr = serv.accept()
    from_client = ''

    while True:
        data = conn.recv(4096)
        if not data: break
        from_client += data.decode()
        print(from_client)

        conn.send(b'I am SERVER\n')

    conn.close()
    print('client disconnected')

if __name__ == '__main__':
    main()
