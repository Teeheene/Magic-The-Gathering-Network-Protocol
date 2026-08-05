from typing import List, Dict, Any, Optional, Callable
from app.server.game.game_state import GameState
from app.server.interfaces import TransportInterface, SeqNumProvider

class StackItem:
    def __init__(self, stack_item_id: str, item_type: str, source: str, controller: str, targets: List[str], effect_fn: Optional[Callable] = None, effect_payload: Optional[Dict[str, Any]] = None):
        self.stack_item_id = stack_item_id
        self.item_type = item_type # SPELL | ABILITY | TRIGGER_ABILITY
        self.source = source
        self.controller = controller
        self.targets = list(targets)
        self.effect_fn = effect_fn
        self.effect_payload = effect_payload or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "stack_item_id": self.stack_item_id,
            "item_type": self.item_type,
            "source": self.source,
            "targets": list(self.targets),
            "controller": self.controller
        }

class GameStack:
    def __init__(self, game_state: GameState, transport: Optional[TransportInterface] = None, seq_num_provider: Optional[SeqNumProvider] = None):
        self.game_state = game_state
        self.transport = transport
        self.seq_num_provider = seq_num_provider
        self._items: List[StackItem] = []
        self._next_id = 1

    def generate_stack_item_id(self) -> str:
        item_id = f"stk_{self._next_id:02d}"
        self._next_id += 1
        return item_id

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def push(self, item: StackItem) -> None:
        self._items.append(item)
        self.game_state.stack.append(item.to_dict())

        if self.transport and self.seq_num_provider:
            seq = self.seq_num_provider.next_seq_num()
            push_pdu = {
                "type": "STACK_PUSH",
                "seq_num": seq,
                "stack_item_id": item.stack_item_id,
                "item_type": item.item_type,
                "source": item.source,
                "targets": item.targets,
                "controller": item.controller
            }
            self.transport.broadcast(push_pdu)

    def peek(self) -> Optional[StackItem]:
        if not self._items:
            return None
        return self._items[-1]

    def pop(self) -> Optional[StackItem]:
        if not self._items:
            return None
        item = self._items.pop()
        if self.game_state.stack:
            self.game_state.stack.pop()
        return item

    def remove_item(self, stack_item_id: str) -> Optional[StackItem]:
        for idx, item in enumerate(self._items):
            if item.stack_item_id == stack_item_id:
                removed = self._items.pop(idx)
                if idx < len(self.game_state.stack):
                    self.game_state.stack.pop(idx)
                return removed
        return None

    def validate_targets(self, item: StackItem, validate_target_fn: Optional[Callable[[str, StackItem, GameState], bool]] = None) -> bool:
        if not item.targets:
            return True
        
        has_at_least_one_legal = False
        for t in item.targets:
            is_legal = True
            if validate_target_fn:
                is_legal = validate_target_fn(t, item, self.game_state)
            else:
                # Default validation: check if player_id or existing permanent on battlefield or item in stack
                if t in self.game_state.players:
                    is_legal = True
                elif self.game_state.get_permanent(t) is not None:
                    is_legal = True
                elif any(stk["stack_item_id"] == t for stk in self.game_state.stack):
                    is_legal = True
                else:
                    is_legal = False
            
            if is_legal:
                has_at_least_one_legal = True
                break
        return has_at_least_one_legal

    def resolve_top(self, validate_target_fn: Optional[Callable[[str, StackItem, GameState], bool]] = None) -> Dict[str, Any]:
        if self.is_empty():
            return {"result": "EMPTY"}

        item = self.pop()
        if item is None:
            return {"result": "EMPTY"}

        targets_valid = self.validate_targets(item, validate_target_fn)

        seq = self.seq_num_provider.next_seq_num() if self.seq_num_provider else 0
        state_changes: List[Dict[str, Any]] = []

        if not targets_valid:
            resolve_pdu = {
                "type": "STACK_RESOLVE",
                "seq_num": seq,
                "stack_item_id": item.stack_item_id,
                "result": "FIZZLE",
                "state_changes": []
            }
            if self.transport:
                self.transport.broadcast(resolve_pdu)
            return {"result": "FIZZLE", "item": item, "pdu": resolve_pdu}

        if item.effect_fn:
            state_changes = item.effect_fn(item, self.game_state) or []

        resolve_pdu = {
            "type": "STACK_RESOLVE",
            "seq_num": seq,
            "stack_item_id": item.stack_item_id,
            "result": "RESOLVED",
            "state_changes": state_changes
        }
        if self.transport:
            self.transport.broadcast(resolve_pdu)

        return {"result": "RESOLVED", "item": item, "state_changes": state_changes, "pdu": resolve_pdu}
