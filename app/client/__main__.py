import argparse

from app.client.cli import (
    ask_to_try_again,
    mulligan_screen,
    prompt_connection_setup,
    prompt_deck_setup,
    prompt_join_lobby,
    show_connection_error,
    show_returning_to_connection,
    wait_for_phase,
)
from app.client.connection import ClientConnection
from app.client.pdu_dispatcher import PduDispatcher
from app.client.state import ClientState


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Run the MTGP command-line client.")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="server hostname or IP address (default: %(default)s)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=4444,
        help="server TCP port (default: %(default)s)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print encoded and decoded protocol messages",
    )
    return parser.parse_args(argv)


def connection_screen(args):
    username = prompt_connection_setup(args.host, args.port)
    deck_list = prompt_deck_setup()

    client = ClientConnection(args.host, args.port, args.verbose)
    try:
        client.connect()
    except OSError as error:
        show_connection_error(error)
        client.close()
        return None

    state = ClientState(username)
    state.deck_list = [card.card_id for card in deck_list]
    dispatcher = PduDispatcher(state, client)
    client.pdu_handler = dispatcher.handle

    prompt_join_lobby()
    dispatcher.send_player_ready()
    if not wait_for_phase(dispatcher, "MULLIGAN"):
        return dispatcher

    mulligan_screen(dispatcher)
    return dispatcher


def main(argv=None):
    args = parse_args(argv)

    while True:
        dispatcher = connection_screen(args)

        if (
            dispatcher is not None
            and dispatcher.state.current_state.get("phase") == "LOBBY"
        ):
            dispatcher.connection.close()
            show_returning_to_connection()
            continue

        if not ask_to_try_again():
            if dispatcher is not None:
                dispatcher.connection.close()
            return

        if dispatcher is not None:
            dispatcher.connection.close()


if __name__ == "__main__":
    main()
