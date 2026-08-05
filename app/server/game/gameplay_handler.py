from typing import Dict, Any, List, Optional, Tuple
from app.server.game.game_state import GameState
from app.server.game.stack import GameStack, StackItem
from app.server.game.priority import PriorityManager
from app.server.game.cards import CardCatalog, CardInstance, CardDefinition
from app.server.game.mana import ManaPayment
from app.server.game.effect_handlers import get_effect_handler
from app.server.interfaces import PhaseManagerInterface

class GameplayHandler:
    def __init__(self, game_state: GameState, stack: GameStack, priority_mgr: PriorityManager, phase_manager: Optional[PhaseManagerInterface] = None):
        self.game_state = game_state
        self.stack = stack
        self.priority_mgr = priority_mgr
        self.phase_manager = phase_manager
        self.catalog = CardCatalog.get_instance()

    def play_land(self, player_id: str, card_id: str) -> Dict[str, Any]:
        if self.game_state.priority_holder != player_id:
            return {"status": "ERROR", "code": "NOT_YOUR_PRIORITY", "message": "You do not hold priority."}

        current_phase = self.phase_manager.get_current_phase() if self.phase_manager else self.game_state.phase
        if current_phase not in ("PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"):
            return {"status": "ERROR", "code": "WRONG_PHASE", "message": "Lands can only be played during Main Phase."}

        active_player = self.phase_manager.get_active_player() if self.phase_manager else self.game_state.active_player
        if player_id != active_player:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Only Active Player can play a land."}

        if self.game_state.land_played_this_turn:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Already played a land this turn."}

        hand = self.game_state.hands.get(player_id, [])
        if card_id not in hand:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Card not in hand."}

        definition = self.catalog.get_definition(card_id)
        if not definition or not definition.is_land():
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Card is not a land."}

        # Remove from hand, place on battlefield
        hand.remove(card_id)
        self.game_state.battlefield[player_id].append({
            "id": card_id,
            "tapped": False
        })
        self.game_state.land_played_this_turn = True
        if self.phase_manager:
            self.phase_manager.mark_land_played()

        # Re-issue priority grant to AP
        self.priority_mgr.grant_priority(player_id)
        return {"status": "SUCCESS", "action": "PLAY_LAND", "card_id": card_id}

    def cast_spell(self, player_id: str, card_id: str, targets: List[str], mana_payment: Dict[str, int]) -> Dict[str, Any]:
        if self.game_state.priority_holder != player_id:
            return {"status": "ERROR", "code": "NOT_YOUR_PRIORITY", "message": "You do not hold priority."}

        hand = self.game_state.hands.get(player_id, [])
        if card_id not in hand:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Card not in hand."}

        definition = self.catalog.get_definition(card_id)
        if not definition:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Unknown card."}

        current_phase = self.phase_manager.get_current_phase() if self.phase_manager else self.game_state.phase
        active_player = self.phase_manager.get_active_player() if self.phase_manager else self.game_state.active_player

        # Sorcery-speed timing check
        if not definition.is_instant():
            if player_id != active_player:
                return {"status": "ERROR", "code": "WRONG_PHASE", "message": "Non-instants require sorcery speed (Active Player)." }
            if current_phase not in ("PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"):
                return {"status": "ERROR", "code": "WRONG_PHASE", "message": "Non-instants require Main Phase."}
            if not self.stack.is_empty():
                return {"status": "ERROR", "code": "WRONG_PHASE", "message": "Non-instants require empty stack."}

        # Validate & execute mana payment
        success, err_msg, tapped_sources = ManaPayment.execute_payment(player_id, definition.mana_cost, mana_payment, self.game_state)
        if not success:
            return {"status": "ERROR", "code": "INSUFFICIENT_MANA", "message": err_msg}

        # Remove card from hand
        hand.remove(card_id)

        base_id = self.catalog.extract_base_id(card_id)
        handler_fn = get_effect_handler(base_id)

        # Define resolution effect wrapper
        def make_resolution_effect(def_obj: CardDefinition, c_id: str, ctrl: str, h_fn: Optional[Any]):
            def effect_fn(item: StackItem, state: GameState, game_stack: Optional[Any] = None) -> List[Dict[str, Any]]:
                changes = []
                stk = game_stack or self.stack
                if h_fn:
                    changes = h_fn(item, state, stk) or []

                if def_obj.is_permanent():
                    instance = CardInstance(c_id, def_obj, ctrl)
                    state.battlefield[ctrl].append(instance.to_battlefield_dict())
                    changes.append({
                        "change_type": "PERMANENT_ENTERS",
                        "card_id": c_id,
                        "controller": ctrl,
                        "tapped": False
                    })
                else:
                    state.graveyards[ctrl].append(c_id)
                    changes.append({
                        "change_type": "SPELL_RESOLVED_TO_GRAVEYARD",
                        "card_id": c_id,
                        "controller": ctrl
                    })
                return changes
            return effect_fn

        stack_item_id = self.stack.generate_stack_item_id()
        stack_item = StackItem(
            stack_item_id=stack_item_id,
            item_type="SPELL",
            source=card_id,
            controller=player_id,
            targets=targets,
            effect_fn=make_resolution_effect(definition, card_id, player_id, handler_fn)
        )

        self.stack.push(stack_item)
        self.priority_mgr.handle_action(player_id)

        return {"status": "SUCCESS", "action": "CAST_SPELL", "stack_item_id": stack_item_id}

    def activate_ability(self, player_id: str, source_id: str, ability_index: int, targets: List[str], cost_payment: Dict[str, Any]) -> Dict[str, Any]:
        if self.game_state.priority_holder != player_id:
            return {"status": "ERROR", "code": "NOT_YOUR_PRIORITY", "message": "You do not hold priority."}

        perm = self.game_state.get_permanent(source_id)
        if not perm:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Source permanent not on battlefield."}

        if self.game_state.get_permanent_controller(source_id) != player_id:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "You do not control this permanent."}

        if cost_payment.get("tap", False):
            if perm.get("tapped", False):
                return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Permanent is already tapped."}
            perm["tapped"] = True

        base_id = self.catalog.extract_base_id(source_id)
        handler_fn = get_effect_handler(base_id)

        stack_item_id = self.stack.generate_stack_item_id()
        stack_item = StackItem(
            stack_item_id=stack_item_id,
            item_type="ABILITY",
            source=source_id,
            controller=player_id,
            targets=targets,
            effect_fn=handler_fn
        )

        self.stack.push(stack_item)
        self.priority_mgr.handle_action(player_id)

        return {"status": "SUCCESS", "action": "ACTIVATE_ABILITY", "stack_item_id": stack_item_id}
