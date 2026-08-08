"""Coordinates the graphical client, network transport, and client state."""

import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from app.client.gui import GraphicalGameClient
from app.client.state import ClientState
from app.client.transport import ClientTransport


class ClientApplication:
    """Own the objects that need to live for the entire client session."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        verbose: bool = False,
        player_id: Optional[str] = None,
    ) -> None:
        self.initial_host = host or "127.0.0.1"
        self.initial_port = port or 4444
        self.initial_player_id = player_id.strip() if player_id else ""

        # The application owns one transport and one authoritative client
        # state. The GUI only displays them and requests actions through callbacks.
        self.transport = ClientTransport(verbose=verbose)
        self.connection_generation = 0
        self._heartbeat_stop = threading.Event()
        self._pong_received = threading.Event()
        self._ready_condition = threading.Condition()
        self._awaiting_ready = False
        self._ready_response: Optional[Dict[str, Any]] = None
        self.client_state = ClientState(player_id=self.initial_player_id)
        self.window = GraphicalGameClient(
            send_action_fn=self.send_action,
            client_state=self.client_state,
            connect_fn=self.connect_to_server,
            disconnect_fn=self.disconnect_from_server,
            initial_host=self.initial_host,
            initial_port=self.initial_port,
            initial_player_id=self.initial_player_id,
        )

    def run(self) -> None:
        """Run Tk's event loop and close the socket when the window exits."""
        try:
            self.window.mainloop()
        finally:
            self.disconnect_from_server()

    def send_action(self, pdu: Dict[str, Any]) -> None:
        """Send an action created by the GUI through the active connection."""
        try:
            self.transport.send_pdu(pdu)
        except Exception as exc:
            print(f"Send error: {exc}")

    def connect_to_server(
        self,
        host: str,
        port: int,
        player_id: str,
        deck_list: List[str],
    ) -> Tuple[bool, str]:
        """Connect and complete PLAYER_READY before allowing game entry."""
        # GraphicalGameClient invokes this callback from a worker thread, so
        # waiting on the socket here does not freeze Tk's event loop.
        # GAME_OVER returns to LOBBY on the same socket. A subsequent Begin
        # therefore sends a fresh PLAYER_READY instead of reconnecting.
        if self.transport.sock is not None:
            self.client_state.player_id = player_id
            self.client_state.reset_for_lobby()
            try:
                with self._ready_condition:
                    self._awaiting_ready = True
                    self._ready_response = None
                self.transport.send_pdu(self.client_state.build_player_ready(deck_list))
                with self._ready_condition:
                    self._ready_condition.wait_for(lambda: self._ready_response is not None, timeout=5)
                    response = self._ready_response
                    self._awaiting_ready = False
                if response is None:
                    self.disconnect_from_server()
                    return False, "The server did not answer PLAYER_READY in time."
                if response.get("type") == "ERROR":
                    return False, response.get("message", "The server rejected PLAYER_READY.")
                return True, "Ready. Waiting for the other player."
            except Exception as exc:
                with self._ready_condition:
                    self._awaiting_ready = False
                self.disconnect_from_server()
                return False, f"Could not re-enter the lobby: {exc}"

        connection_generation = self.connection_generation
        self.client_state.player_id = player_id
        try:
            self.transport.connect(host, port)
            self.transport.send_pdu(self.client_state.build_player_ready(deck_list))
            response = self.transport.read_pdu()
        except Exception as exc:
            self.transport.close()
            return False, f"Could not connect: {exc}"

        if not response:
            self.transport.close()
            return False, "The server closed the connection before accepting the player."
        if response.get("type") == "ERROR":
            self.transport.close()
            return False, response.get("message", "The server rejected the connection setup.")
        if response.get("type") != "GAME_STATE_UPDATE" or response.get("state", {}).get("phase") != "LOBBY":
            self.transport.close()
            return False, "The server returned an unexpected handshake response."

        # Only an accepted player gets a persistent server-listener thread.
        self.client_state.player_id = player_id
        self.window.enqueue_pdu(response)
        self._heartbeat_stop.clear()
        threading.Thread(
            target=self.listen_for_server_updates,
            args=(connection_generation,),
            daemon=True,
        ).start()
        threading.Thread(target=self._heartbeat_loop, args=(connection_generation,), daemon=True).start()
        return True, "Connected. Waiting for the other player."

    def disconnect_from_server(self) -> None:
        """Invalidate the current listener and close its socket."""
        self.connection_generation += 1
        self._heartbeat_stop.set()
        self.transport.close()

    def listen_for_server_updates(self, connection_generation: int) -> None:
        """Read server PDUs and hand them to Tk through its thread-safe queue."""
        while connection_generation == self.connection_generation:
            try:
                pdu = self.transport.read_pdu()
                if not pdu:
                    break
                if pdu.get("type") == "PONG":
                    self._pong_received.set()
                with self._ready_condition:
                    is_ready_reply = self._awaiting_ready and (
                        pdu.get("type") == "ERROR"
                        or (pdu.get("type") == "GAME_STATE_UPDATE" and pdu.get("state", {}).get("phase") == "LOBBY")
                    )
                    if is_ready_reply:
                        self._ready_response = pdu
                        self._ready_condition.notify_all()
                        continue
                self.window.enqueue_pdu(pdu)
            except Exception:
                break

    def _heartbeat_loop(self, connection_generation: int) -> None:
        while not self._heartbeat_stop.wait(30):
            if connection_generation != self.connection_generation:
                return
            self._pong_received.clear()
            try:
                self.transport.send_pdu(self.client_state.build_ping(int(time.time() * 1000)))
            except Exception:
                return
            if not self._pong_received.wait(10):
                self.transport.close()
                return


def run_client_app(
    host: Optional[str] = None,
    port: Optional[int] = None,
    verbose: bool = False,
    player_id: Optional[str] = None,
) -> None:
    """Construct and run the graphical client application."""
    ClientApplication(host, port, verbose, player_id).run()
