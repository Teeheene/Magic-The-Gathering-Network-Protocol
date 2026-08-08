from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, List

class TransportInterface(ABC):
    @abstractmethod
    def send_to_player(self, player_id: str, pdu: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def broadcast(self, pdu: Dict[str, Any]) -> None:
        pass

class PhaseManagerInterface(ABC):
    @abstractmethod
    def get_current_phase(self) -> str:
        pass

    @abstractmethod
    def get_active_player(self) -> str:
        pass

    @abstractmethod
    def is_main_phase(self) -> bool:
        pass

    @abstractmethod
    def advance_phase(self) -> None:
        pass

    @abstractmethod
    def get_turn_number(self) -> int:
        pass

    @abstractmethod
    def has_land_been_played(self) -> bool:
        pass

    @abstractmethod
    def mark_land_played(self) -> None:
        pass

    @abstractmethod
    def is_first_turn_first_player(self) -> bool:
        pass

class SeqNumProvider(ABC):
    @abstractmethod
    def next_seq_num(self) -> int:
        pass
