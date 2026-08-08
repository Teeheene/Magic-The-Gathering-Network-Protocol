"""Command-line entry point for the MTGNP server."""

import argparse

from app.server.network.server import Server


def main() -> None:
    parser = argparse.ArgumentParser(description="MTGNP 1.0 server")
    parser.add_argument("--host", default="0.0.0.0", help="Interface to bind")
    parser.add_argument("--port", type=int, default=4444, help="TCP port to bind")
    args = parser.parse_args()
    Server(host=args.host, port=args.port).start()


if __name__ == "__main__":
    main()
