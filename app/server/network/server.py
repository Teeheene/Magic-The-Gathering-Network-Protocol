"""Persistent two-seat MTGNP TCP lobby server."""

from __future__ import annotations

import queue
import socket
import threading
from typing import Any, Dict, List, Optional, Tuple

from app.server.core.player import Player, ProtocolDecodeError
from app.server.game.session import GameSession
from app.shared.cards import validate_deck


class Server:
    """Keep two TCP seats alive across any number of games."""

    MAX_PAYLOAD_SIZE = 65535

    def __init__(self, host: str = "0.0.0.0", port: int = 4444, max_clients: int = 2):
        if max_clients != 2:
            raise ValueError("MTGNP 1.0 requires exactly two client seats.")
        self.host = host
        self.port = port
        self.max_clients = max_clients
        self.running = False
        self.players: List[Player] = []
        self.session = GameSession(max_clients)
        self.next_id = 0
        self.seq_num = 0
        self._inbound: queue.Queue[Tuple[Player, Optional[Dict[str, Any]], Optional[Exception]]] = queue.Queue()
        self._pending_connections: queue.Queue[Tuple[socket.socket, Any]] = queue.Queue()

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.port = self.sock.getsockname()[1]
        self.sock.listen(max_clients)
        print(f"Server running on {self.host}:{self.port}")

    def start(self) -> None:
        self.running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        try:
            while self.running:
                self._reset_lobby_submissions()
                print("Lobby open. Waiting for two PLAYER_READY submissions...")
                if not self._run_lobby():
                    continue

                self.session = GameSession(self.max_clients, players=list(self.players))
                self.session.start()
                print("Both players ready. Game setup and mulligans started.")
                self._run_game()
                if self.running:
                    print("Game ended. Returning existing connections to the lobby...")
        finally:
            self._close_all_players()

    def _accept_loop(self) -> None:
        while self.running:
            try:
                conn, addr = self.sock.accept()
            except OSError:
                return
            if len(self.players) + self._pending_connections.qsize() >= self.max_clients:
                conn.close()
                continue
            self._pending_connections.put((conn, addr))

    def _read_player_loop(self, player: Player) -> None:
        while self.running and player in self.players:
            try:
                pdu = player.receive()
                self._inbound.put((player, pdu, None))
                if pdu is None:
                    return
            except ProtocolDecodeError as exc:
                if exc.recoverable:
                    try:
                        self._send_error(player, "INVALID_JSON", str(exc), {})
                    except Exception:
                        self._inbound.put((player, None, exc))
                        return
                    continue
                self._inbound.put((player, None, exc))
                return
            except Exception as exc:
                self._inbound.put((player, None, exc))
                return

    def _run_lobby(self) -> bool:
        while self.running:
            self._seat_pending_connections()
            try:
                player, pdu, error = self._inbound.get(timeout=0.1)
            except queue.Empty:
                continue
            if player not in self.players:
                continue
            if error or pdu is None:
                self._remove_player(player)
                continue
            if not isinstance(pdu, dict):
                self._send_error(player, "INVALID_JSON", "PDU must be a JSON object.", {})
                continue
            if pdu.get("type") == "PING":
                if not self._valid_ping(pdu):
                    self._send_error(player, "ILLEGAL_ACTION", "PING requires integer seq_num and timestamp fields.", pdu)
                    continue
                self._send_pong(player, pdu)
                if player.player_id and isinstance(pdu.get("seq_num"), int):
                    self.session.last_sent_seq_nums[player.player_id] = pdu["seq_num"]
                continue
            if pdu.get("type") != "PLAYER_READY":
                self._send_error(player, "UNKNOWN_TYPE", "LOBBY only accepts PLAYER_READY or PING.", pdu)
                continue
            if self._accept_player_ready(player, pdu):
                self._send_lobby_state(player)
                if len(self.players) == self.max_clients and all(p.player_id and p.deck_list for p in self.players):
                    return True
        return False

    def _seat_pending_connections(self) -> None:
        while len(self.players) < self.max_clients:
            try:
                conn, addr = self._pending_connections.get_nowait()
            except queue.Empty:
                return
            player = Player(self.next_id, conn)
            self.next_id += 1
            self.players.append(player)
            threading.Thread(target=self._read_player_loop, args=(player,), daemon=True).start()
            print(f"Player connected on {addr[0]}:{addr[1]}")

    def _run_game(self) -> None:
        while self.running and self.session.running:
            timeout = self.session.seconds_until_priority_timeout()
            if timeout is not None and timeout <= 0:
                self._expire_priority_holder()
                break
            try:
                player, pdu, error = self._inbound.get(timeout=timeout)
            except queue.Empty:
                self._expire_priority_holder()
                break
            if player not in self.players:
                continue
            if error or pdu is None:
                self.session.handle_disconnect(player)
                self._remove_player(player)
                break
            if pdu.get("type") == "PING":
                if not self._valid_ping(pdu):
                    self.session._send_error(player, "ILLEGAL_ACTION", "PING requires integer seq_num and timestamp fields.", pdu)
                    continue
                self._send_pong(player, pdu)
                continue
            self.session.handle_pdu(player, pdu)

    def _expire_priority_holder(self) -> None:
        timed_out_id = self.session.game_state.priority_holder if self.session.game_state else None
        self.session.handle_priority_timeout()
        timed_out_player = next((p for p in self.players if p.player_id == timed_out_id), None)
        if timed_out_player:
            self._remove_player(timed_out_player)

    def _accept_player_ready(self, player: Player, ready_pdu: Optional[Dict[str, Any]] = None) -> bool:
        """Validate or replace one seat's lobby submission without disconnecting it."""
        if ready_pdu is None:
            try:
                ready_pdu = player.receive()
            except Exception as exc:
                self._send_error(player, "INVALID_JSON", str(exc), {})
                return False
        if not isinstance(ready_pdu, dict) or ready_pdu.get("type") != "PLAYER_READY":
            self._send_error(player, "UNKNOWN_TYPE", "Expected PLAYER_READY.", ready_pdu or {})
            return False
        if not isinstance(ready_pdu.get("seq_num"), int):
            self._send_error(player, "ILLEGAL_ACTION", "PLAYER_READY requires an integer seq_num.", ready_pdu)
            return False

        requested_id = ready_pdu.get("player_id")
        if not isinstance(requested_id, str) or not requested_id.strip():
            self._send_error(player, "ILLEGAL_ACTION", "player_id must be a non-empty string.", ready_pdu)
            return False
        requested_id = requested_id.strip()
        if any(
            other is not player and other.player_id
            and other.player_id.casefold() == requested_id.casefold()
            for other in self.players
        ):
            self._send_error(player, "DUPLICATE_ID", f"Player ID '{requested_id}' is already claimed.", ready_pdu)
            return False

        deck_list = ready_pdu.get("deck_list")
        valid, message = validate_deck(deck_list)
        if not valid:
            self._send_error(player, "ILLEGAL_DECK", message, ready_pdu)
            return False
        player.player_id = requested_id
        player.deck_list = list(deck_list)
        return True

    def _send_lobby_state(self, player: Player) -> None:
        ready_count = sum(bool(p.player_id and p.deck_list) for p in self.players)
        waiting_for = [f"player_{index + 1}" for index, p in enumerate(self.players) if not (p.player_id and p.deck_list)]
        waiting_for.extend(
            f"player_{index + 1}" for index in range(len(self.players), self.max_clients)
        )
        player.send({
            "type": "GAME_STATE_UPDATE",
            "seq_num": self._next_seq(),
            "state": {"phase": "LOBBY", "players_ready": ready_count, "waiting_for": waiting_for},
        })

    def _send_error(self, player: Player, code: str, message: str, rejected: Dict[str, Any]) -> None:
        seq = rejected.get("seq_num") if isinstance(rejected.get("seq_num"), int) else self._next_seq()
        player.send({
            "type": "ERROR", "seq_num": seq, "code": code,
            "message": message, "rejected_action": rejected,
        })

    @staticmethod
    def _send_pong(player: Player, ping: Dict[str, Any]) -> None:
        player.send({"type": "PONG", "seq_num": ping.get("seq_num", 0), "timestamp": ping.get("timestamp")})

    @staticmethod
    def _valid_ping(ping: Dict[str, Any]) -> bool:
        return (
            isinstance(ping.get("seq_num"), int)
            and not isinstance(ping.get("seq_num"), bool)
            and isinstance(ping.get("timestamp"), int)
            and not isinstance(ping.get("timestamp"), bool)
        )

    def _reset_lobby_submissions(self) -> None:
        for player in self.players:
            player.player_id = None
            player.deck_list = []

    def _remove_player(self, player: Player) -> None:
        if player in self.players:
            self.players.remove(player)
        player.close()

    def _close_all_players(self) -> None:
        for player in list(self.players):
            self._remove_player(player)

    def _next_seq(self) -> int:
        self.seq_num += 1
        return self.seq_num

    def stop(self) -> None:
        self.running = False
        self.session.running = False
        self._close_all_players()
        try:
            self.sock.close()
        except Exception:
            pass
