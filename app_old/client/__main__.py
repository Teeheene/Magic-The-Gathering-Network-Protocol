"""Minimal command-line entry point for the graphical MTGNP client."""

import argparse

from app.client.application import run_client_app


def main() -> None:
    # These arguments only prefill/configure the graphical application.
    parser = argparse.ArgumentParser(description="MTGNP Client Launcher")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose raw PDU logging")
    parser.add_argument("--host", type=str, default=None, help="Prefill the server host")
    parser.add_argument("--port", type=int, default=None, help="Prefill the server port")
    parser.add_argument("--player-id", type=str, default=None, help="Prefill the player ID")
    args = parser.parse_args()

    # Networking, state, and UI coordination live in application.py.
    run_client_app(
        host=args.host,
        port=args.port,
        verbose=args.verbose,
        player_id=args.player_id,
    )


if __name__ == "__main__":
    main()
