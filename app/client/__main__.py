from app.client.connection import ClientConnection
from app.client.deck_builder import choose_deck
from app.client.pdu_dispatcher import PduDispatcher
from app.client.state import ClientState
import time


def wait_for_update(dispatcher, previous_seq_num):
    while dispatcher.connection.running:
        if dispatcher.state.last_error is not None:
            print(f"> Server error: {dispatcher.state.last_error['message']}")
            return False
        if dispatcher.state.latest_seq_num != previous_seq_num:
            return True
        time.sleep(0.05)
    return False

def game_screen(dispatcher):
    print("==== GAME PHASE ====")
    print("Still in the works")
    input("> Choice? ")

def mulligan_screen(dispatcher):
    print("\n==== MULLIGAN PHASE ====")
    print("Y = draw a new hand | N = keep this hand")

    mulligans_taken = 0

    while dispatcher.connection.running:
        if dispatcher.state.local_hand:
            print(f"> Your hand: {dispatcher.state.local_hand}")

        choice = input("> MULLIGAN (Y/N)? ").strip().casefold()

        if choice == "y":
            previous_seq_num = dispatcher.state.latest_seq_num
            dispatcher.state.last_error = None
            dispatcher.send_mulligan_choice(False, [])
            if not wait_for_update(dispatcher, previous_seq_num):
                continue
            mulligans_taken += 1
            print(
                "> New hand requested. When you keep, bottom "
                f"{mulligans_taken} card(s)."
            )
            continue

        if choice == "n":
            cards_to_bottom = []

            while len(cards_to_bottom) != mulligans_taken:
                if mulligans_taken == 0:
                    break

                cards_to_bottom = input(
                    f"> Enter {mulligans_taken} card ID(s) to bottom, "
                    "separated by spaces: "
                ).strip().split()

                if len(cards_to_bottom) != mulligans_taken:
                    print(f"> Enter exactly {mulligans_taken} card ID(s).")
                    cards_to_bottom = []

            previous_seq_num = dispatcher.state.latest_seq_num
            dispatcher.state.last_error = None
            dispatcher.send_mulligan_choice(True, cards_to_bottom)
            if not wait_for_update(dispatcher, previous_seq_num):
                continue
            print("> Hand kept.")
            game_screen(dispatcher)

        print("> Please enter Y or N.")


def connection_screen():
    print("==== MTGP CLIENT ====")
    print("Connection Setup")
    # host = input("> Host (127.0.0.1): ")
    # port = int(input("> Port (4444): "))
    username = input("> Username: ")

    host = "127.0.0.1"
    port = 4444

    print("Deck Setup")
    deck_list = choose_deck()
    print(f"> Deck ready: {len(deck_list)} cards")

    client = ClientConnection(host, port, True)
    client.connect()

    # Initialize client state and PDU dispatcher.
    state = ClientState(username)
    state.deck_list = [card.card_id for card in deck_list]
    dispatcher = PduDispatcher(state, client)
    client.pdu_handler = dispatcher.handle

    print("\nPress 'Enter' to join lobby")
    while client.running:
        command = input("> ")
        if command.strip().casefold() == "enter":
            dispatcher.send_player_ready()
            while client.running and state.phase != "MULLIGAN":
                if state.last_error is not None:
                    print(f"> Server error: {state.last_error['message']}")
                    return dispatcher
                time.sleep(0.05)
            if not client.running:
                return dispatcher
            mulligan_screen(dispatcher)
            return dispatcher

def main():
    connection_screen()


if __name__ == "__main__":
    main()
