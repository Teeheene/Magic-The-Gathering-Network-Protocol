from app.client.connection import ClientConnection
from app.client.deck_builder import choose_deck
from app.client.pdu_dispatcher import PduDispatcher
from app.client.state import ClientState


def connection_screen():
    print("==== MTGP CLIENT ====")
    print("Connection Setup")
    # host = input("> Host (127.0.0.1): ")
    # port = int(input("> Port (4444): "))
    # username = input("> Username: ")

    host = "127.0.0.1"
    port = 4444
    username = "Teehee"

    print("Deck Setup")
    deck_list = choose_deck()
    print(f"> Deck ready: {len(deck_list)} cards")

    client = ClientConnection(host, port, True)
    client.connect()

    # Initialize client state and PDU dispatcher.
    state = ClientState(username)
    state.deck_list = [card.card_id for card in deck_list]
    dispatcher = PduDispatcher(state, client)

    print("\nPress 'Enter' to join lobby")
    while client.running:
        command = input("> ")
        if command == "Enter":
            dispatcher.send_player_ready()

def main():
    connection_screen()


if __name__ == "__main__":
    main()
