from typing import Dict, Any, List, Callable

class GameEvent:
    def __init__(self, event_type: str, data: Dict[str, Any]):
        self.event_type = event_type
        self.data = data

class EventBus:
    def __init__(self):
        self.listeners: Dict[str, List[Callable[[GameEvent], None]]] = {}

    def subscribe(self, event_type: str, listener: Callable[[GameEvent], None]) -> None:
        self.listeners.setdefault(event_type, []).append(listener)

    def publish(self, event: GameEvent) -> None:
        for listener in self.listeners.get(event.event_type, []):
            listener(event)
