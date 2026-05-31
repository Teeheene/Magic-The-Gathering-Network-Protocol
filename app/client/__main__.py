import socket

# TODO
# <> abstract client from main 

# sample client
def main():
    HOST = input("Enter host: ")
    PORT = int(input("Enter port: "))
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # test conn
    client.connect((HOST, PORT))

    while 1:
        data = str(client.recv(1024), "utf-8")
        received = "server..." + data
        if not data:
            break

        print(received)

if __name__ == '__main__':
    main()

