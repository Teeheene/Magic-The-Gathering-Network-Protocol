from app.client.connection import ClientConnection

def connection_screen():
    print("==== MTGP CLIENT ====")
    username = input("User: ")
    deck = input("Deck: ")

    client = ClientConnection()
    client.connect()

    print("\nPress 'Enter' to join lobby")
    while client.running:
        command = input("> ")

        if command == "Enter":
            client.join_lobby(username)


def main():
    connection_screen()

if __name__ == "__main__":
    main()