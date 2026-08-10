import argparse
from app.server.connection import ServerConnection


def main():
    parser = argparse.ArgumentParser(description="MTGNP 1.0 server")
    parser.add_argument("--host", default="0.0.0.0", help="Interface to bind")
    parser.add_argument("--port", type=int, default=4444, help="TCP port to bind")
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="print all sent and received PDUs to console",
    )
    args = parser.parse_args()
    server = ServerConnection(
        host=args.host, port=args.port, verbose=args.verbose
    )
    server.start()
    server.wait_for_players()


if __name__ == "__main__":
    main()