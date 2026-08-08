import time
from typing import Optional, Dict, Any, Callable
from app.server.game.game_state import GameState
from app.server.game.stack import GameStack
from app.server.interfaces import TransportInterface, PhaseManagerInterface, SeqNumProvider

class PriorityManager:
    def __init__(self, game_state: GameState, stack: GameStack, phase_manager: Optional[PhaseManagerInterface] = None, transport: Optional[TransportInterface] = None, seq_num_provider: Optional[SeqNumProvider] = None, time_limit_ms: int = 60000):
        self.game_state = game_state
        self.stack = stack
        self.phase_manager = phase_manager
        self.transport = transport
        self.seq_num_provider = seq_num_provider
        self.time_limit_ms = time_limit_ms
        self.consecutive_passes: int = 0
        self.current_priority_seq_num: int = 0
        self.on_empty_stack_passes: Optional[Callable[[], None]] = None
        self.on_post_resolution: Optional[Callable[[], Optional[bool]]] = None
        self.deadline: Optional[float] = None

    def open_priority_window(self) -> None:
        self.consecutive_passes = 0
        active_player = self.phase_manager.get_active_player() if self.phase_manager else self.game_state.active_player
        self.grant_priority(active_player)

    def grant_priority(self, player_id: str) -> int:
        self.game_state.priority_holder = player_id
        seq = self.seq_num_provider.next_seq_num() if self.seq_num_provider else (self.current_priority_seq_num + 1)
        self.current_priority_seq_num = seq
        self.deadline = time.monotonic() + (self.time_limit_ms / 1000.0)

        if self.transport:
            grant_pdu = {
                "type": "PRIORITY_GRANT",
                "player_id": player_id,
                "seq_num": seq,
                "time_limit_ms": self.time_limit_ms
            }
            # PRIORITY_GRANT is addressed only to the player who may act. A
            # subsequent personalized state update keeps both renderings in sync.
            self.transport.send_to_player(player_id, grant_pdu)
        return seq

    def handle_action(self, player_id: str) -> None:
        self.consecutive_passes = 0
        self.grant_priority(player_id)

    def handle_pass(self, player_id: str) -> Dict[str, Any]:
        if self.game_state.priority_holder != player_id:
            return {"status": "ERROR", "code": "NOT_YOUR_PRIORITY"}

        self.consecutive_passes += 1

        if self.consecutive_passes >= 2:
            self.consecutive_passes = 0
            if not self.stack.is_empty():
                resolve_res = self.stack.resolve_top()
                may_grant = True
                if self.on_post_resolution:
                    may_grant = self.on_post_resolution() is not False
                if getattr(self.phase_manager, "running", True) is False:
                    return {"status": "GAME_OVER", "resolve_result": resolve_res}
                if not may_grant:
                    return {"status": "TRIGGERS_PENDING", "resolve_result": resolve_res}
                active_player = self.phase_manager.get_active_player() if self.phase_manager else self.game_state.active_player
                self.grant_priority(active_player)
                return {"status": "RESOLVED", "resolve_result": resolve_res}
            else:
                self.game_state.priority_holder = None
                self.deadline = None
                if self.on_empty_stack_passes:
                    self.on_empty_stack_passes()
                elif self.phase_manager:
                    self.phase_manager.advance_phase()
                return {"status": "WINDOW_CLOSED"}
        else:
            opponent = self.game_state.get_opponent(player_id)
            self.grant_priority(opponent)
            return {"status": "PASSED", "next_player": opponent}

    def seconds_until_timeout(self) -> Optional[float]:
        if self.deadline is None or not self.game_state.priority_holder:
            return None
        return max(0.0, self.deadline - time.monotonic())
