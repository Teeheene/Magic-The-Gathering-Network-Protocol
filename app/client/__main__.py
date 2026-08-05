import argparse
import sys
import threading
from typing import Dict, Any, Optional

from app.client.state import ClientState
from app.client.actions import ClientActionFactory
from app.client.transport import ClientTransport
from app.client.cli import run_cli

def send_framed_pdu(sock, pdu: Dict[str, Any]) -> None:
    t = ClientTransport()
    t.sock = sock
    t.send_pdu(pdu)

def read_framed_pdu(sock) -> Optional[Dict[str, Any]]:
    t = ClientTransport()
    t.sock = sock
    return t.read_pdu()

def run_tkinter_app(host: Optional[str] = None, port: Optional[int] = None, verbose: bool = False, player_id: Optional[str] = None):
    from app.client.gui import GraphicalGameClient
    if not host:
        try:
            host = input("Enter host [127.0.0.1]: ").strip() or "127.0.0.1"
        except Exception:
            host = "127.0.0.1"
    if not port:
        try:
            port_str = input("Enter port [4444]: ").strip() or "4444"
            port = int(port_str)
        except Exception:
            port = 4444
    
    t_obj = ClientTransport(verbose=verbose)
    try:
        t_obj.connect(host, port)
    except Exception as e:
        print(f"Failed to connect to server: {e}")
        return

    def send_act(pdu: Dict[str, Any]):
        try:
            t_obj.send_pdu(pdu)
        except Exception as e:
            print(f"Send error: {e}")

    app = GraphicalGameClient(send_action_fn=send_act, client_state=ClientState(player_id=player_id))

    def listen_loop():
        while True:
            try:
                pdu = t_obj.read_pdu()
                if not pdu:
                    break
                app.enqueue_pdu(pdu)
            except Exception:
                break

    th = threading.Thread(target=listen_loop, daemon=True)
    th.start()
    app.mainloop()

def main():
    parser = argparse.ArgumentParser(description="MTGNP Client Launcher")
    parser.add_argument("--cli", action="store_true", help="Launch in CLI mode")
    parser.add_argument("--qt", action="store_true", help="Launch in PySide6 Qt mode")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose raw PDU logging")
    parser.add_argument("--host", type=str, default=None, help="Server host IP")
    parser.add_argument("--port", type=int, default=None, help="Server port")
    parser.add_argument("--player-id", type=str, default=None, help="Explicit Player ID")

    args = parser.parse_args()

    if args.cli:
        host = args.host or "127.0.0.1"
        port = args.port or 4444
        run_cli(host=host, port=port, verbose=args.verbose, player_id=args.player_id)
    elif args.qt:
        from app.client.qt.application import run_qt_app
        run_qt_app(host=args.host, port=args.port, verbose=args.verbose)
    else:
        run_tkinter_app(host=args.host, port=args.port, verbose=args.verbose, player_id=args.player_id)

if __name__ == "__main__":
    main()
