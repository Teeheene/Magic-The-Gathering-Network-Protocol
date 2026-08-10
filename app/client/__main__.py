import argparse
import sys

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
    parser = argparse.ArgumentParser(description="Run the MTGP client interface.")
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
        "--player-id",
        default=None,
        help="specify player ID directly",
    )
    parser.add_argument(
        "--qt",
        action="store_true",
        help="launch PySide6 graphical interface",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print encoded and decoded protocol messages",
    )
    return parser.parse_args(argv)


def launch_qt_client(args):
    from PySide6.QtWidgets import QApplication
    from app.client.qt.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    pid = args.player_id or "alice"
    state = ClientState(pid)

    conn = ClientConnection(args.host, args.port, args.verbose)
    dispatcher = PduDispatcher(state, conn)
    conn.pdu_handler = dispatcher.handle

    window = MainWindow(state, dispatcher)
    state.on_state_change = lambda: window.state_updated_signal.emit()

    try:
        conn.connect()
        conn.start_heartbeat(dispatcher)
    except OSError as err:
        print(f"Connection failed: {err}")
        return

    window.show()
    sys.exit(app.exec())


def connection_screen(args):
    username = args.player_id or prompt_connection_setup(args.host, args.port)
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
    client.start_heartbeat(dispatcher)

    prompt_join_lobby()
    dispatcher.send_player_ready()

    if not wait_for_phase(dispatcher, "MULLIGAN"):
        return dispatcher

    mulligan_screen(dispatcher)
    return dispatcher


def main(argv=None):
    args = parse_args(argv)

    if args.qt:
        launch_qt_client(args)
        return

    dispatcher = None
    while True:
        if dispatcher is None or not dispatcher.connection.running:
            dispatcher = connection_screen(args)
        else:
            print("\nReturning to Lobby on existing connection...")
            dispatcher.send_player_ready()
            if not wait_for_phase(dispatcher, "MULLIGAN"):
                if not ask_to_try_again():
                    dispatcher.connection.close()
                    return
                dispatcher.connection.close()
                dispatcher = None
                continue
            mulligan_screen(dispatcher)

        if dispatcher is not None and not ask_to_try_again():
            dispatcher.connection.close()
            return



if __name__ == "__main__":
    main()
