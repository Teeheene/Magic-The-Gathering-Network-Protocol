from typing import List, Dict, Optional

class InteractionState:
    def __init__(self):
        self.selected_hand_card: str = ""
        self.selected_permanent: str = ""
        self.selected_stack_item: str = ""
        
        self.is_targeting_mode: bool = False
        self.selected_targets: List[str] = []
        
        self.selected_attackers: List[str] = []
        self.selected_blockers: Dict[str, str] = {} # blocker_id -> attacker_id

        self.action_pending: bool = False

    def clear_selections(self):
        self.selected_hand_card = ""
        self.selected_permanent = ""
        self.selected_stack_item = ""
        self.is_targeting_mode = False
        self.selected_targets = []
        self.selected_attackers = []
        self.selected_blockers = {}
