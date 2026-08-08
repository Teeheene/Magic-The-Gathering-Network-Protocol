from typing import Dict, Any, List, Optional, Tuple
from app.server.game.game_state import GameState
from app.server.game.stack import GameStack, StackItem
from app.server.game.priority import PriorityManager
from app.server.game.cards import CardCatalog, CardInstance, CardDefinition
from app.server.game.mana import ManaPayment
from app.server.game.effect_handlers import get_effect_handler
from app.server.game.events import EventBus, GameEvent
from app.server.interfaces import PhaseManagerInterface

class GameplayHandler:
    MANA_ONLY_SOURCES = {"mountain", "forest", "plains", "island", "swamp", "llanowar_elves", "elvish_mystic", "sol_ring"}
    ACTIVATED_GENERIC_COSTS = {"millstone": 2, "rod_of_ruin": 3}
    def __init__(self, game_state: GameState, stack: GameStack, priority_mgr: PriorityManager, phase_manager: Optional[PhaseManagerInterface] = None, event_bus: Optional[EventBus] = None):
        self.game_state = game_state
        self.stack = stack
        self.priority_mgr = priority_mgr
        self.phase_manager = phase_manager
        self.event_bus = event_bus
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
        if not self.stack.is_empty():
            return {"status": "ERROR", "code": "WRONG_PHASE", "message": "Lands require an empty stack."}

        hand.remove(card_id)
        self.game_state.battlefield[player_id].append({
            "id": card_id,
            "tapped": False
        })
        self.game_state.land_played_this_turn = True
        if self.phase_manager:
            self.phase_manager.mark_land_played()

        if self.event_bus:
            self.event_bus.publish(GameEvent("permanent_entered", {"card_id": card_id, "controller": player_id}))

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
        if definition.is_land():
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Lands cannot be cast as spells."}

        targets_valid, target_message = self._validate_targets(player_id, definition, targets)
        if not targets_valid:
            return {"status": "ERROR", "code": "ILLEGAL_TARGET", "message": target_message}

        current_phase = self.phase_manager.get_current_phase() if self.phase_manager else self.game_state.phase
        active_player = self.phase_manager.get_active_player() if self.phase_manager else self.game_state.active_player

        if not definition.is_instant():
            if player_id != active_player:
                return {"status": "ERROR", "code": "WRONG_PHASE", "message": "Non-instants require sorcery speed (Active Player)." }
            if current_phase not in ("PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"):
                return {"status": "ERROR", "code": "WRONG_PHASE", "message": "Non-instants require Main Phase."}
            if not self.stack.is_empty():
                return {"status": "ERROR", "code": "WRONG_PHASE", "message": "Non-instants require empty stack."}

        success, err_msg, tapped_sources = ManaPayment.execute_payment(player_id, definition.mana_cost, mana_payment, self.game_state)
        if not success:
            return {"status": "ERROR", "code": "INSUFFICIENT_MANA", "message": err_msg}

        hand.remove(card_id)

        base_id = self.catalog.extract_base_id(card_id)
        handler_fn = get_effect_handler(base_id)

        def make_resolution_effect(def_obj: CardDefinition, c_id: str, ctrl: str, h_fn: Optional[Any]):
            def effect_fn(item: StackItem, state: GameState, game_stack: Optional[Any] = None) -> List[Dict[str, Any]]:
                changes = []
                stk = game_stack or self.stack
                if h_fn:
                    changes = h_fn(item, state, stk) or []

                if def_obj.is_permanent():
                    instance = CardInstance(c_id, def_obj, ctrl)
                    permanent_data = instance.to_battlefield_dict()
                    if def_obj.base_id == "pacifism" and item.targets:
                        permanent_data["attached_to"] = item.targets[0]
                    state.battlefield[ctrl].append(permanent_data)
                    changes.append({
                        "change_type": "PERMANENT_ENTERS",
                        "card_id": c_id,
                        "controller": ctrl,
                        "tapped": False
                    })
                    if self.event_bus:
                        self.event_bus.publish(GameEvent("permanent_entered", {"card_id": c_id, "controller": ctrl}))
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

        if self.event_bus:
            self.event_bus.publish(GameEvent("spell_cast", {
                "card_id": card_id,
                "controller": player_id,
                "targets": list(targets),
                "stack_item_id": stack_item_id
            }))
            for target_id in targets:
                self.event_bus.publish(GameEvent("became_target", {
                    "target_id": target_id,
                    "source_id": card_id,
                    "controller": player_id
                }))

        return {"status": "SUCCESS", "action": "CAST_SPELL", "stack_item_id": stack_item_id}

    def activate_ability(self, player_id: str, source_id: str, ability_index: int, targets: List[str], cost_payment: Dict[str, Any]) -> Dict[str, Any]:
        if self.game_state.priority_holder != player_id:
            return {"status": "ERROR", "code": "NOT_YOUR_PRIORITY", "message": "You do not hold priority."}

        perm = self.game_state.get_permanent(source_id)
        if not perm:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Source permanent not on battlefield."}

        if self.game_state.get_permanent_controller(source_id) != player_id:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "You do not control this permanent."}

        definition = self.catalog.get_definition(source_id)
        base_id = self.catalog.extract_base_id(source_id)
        if not definition or ability_index != 0 or ":" not in definition.text:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "That activated ability does not exist."}
        if base_id in self.MANA_ONLY_SOURCES:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Mana production is declared implicitly in mana_payment."}

        targets_valid, target_message = self._validate_targets(player_id, definition, targets, ability=True)
        if not targets_valid:
            return {"status": "ERROR", "code": "ILLEGAL_TARGET", "message": target_message}

        requires_tap = "Tap:" in definition.text or ", Tap:" in definition.text
        if bool(cost_payment.get("tap")) != requires_tap:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "cost_payment.tap does not match the ability cost."}
        if requires_tap and perm.get("tapped", False):
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Permanent is already tapped."}
        if requires_tap and definition.is_creature() and perm.get("summoning_sick", False) and "haste" not in (set(definition.keywords) | set(perm.get("keywords", []))):
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "A summoning-sick creature cannot pay a tap cost."}

        mana_cost = {"Generic": self.ACTIVATED_GENERIC_COSTS.get(base_id, 0)}
        mana_declared = cost_payment.get("mana", {})
        if not isinstance(mana_declared, dict):
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "cost_payment.mana must be an object."}
        if mana_cost["Generic"]:
            success, message, _ = ManaPayment.execute_payment(player_id, mana_cost, mana_declared, self.game_state)
            if not success:
                return {"status": "ERROR", "code": "INSUFFICIENT_MANA", "message": message}
        if base_id == "mother_of_runes" and cost_payment.get("color") not in {"W", "U", "B", "R", "G"}:
            return {"status": "ERROR", "code": "ILLEGAL_ACTION", "message": "Mother of Runes requires color W, U, B, R, or G."}

        if requires_tap:
            perm["tapped"] = True

        handler_fn = get_effect_handler(base_id)

        stack_item_id = self.stack.generate_stack_item_id()
        stack_item = StackItem(
            stack_item_id=stack_item_id,
            item_type="ABILITY",
            source=source_id,
            controller=player_id,
            targets=targets,
            effect_fn=handler_fn,
            effect_payload={"cost_payment": dict(cost_payment)},
        )

        self.stack.push(stack_item)

        if self.event_bus:
            self.event_bus.publish(GameEvent("ability_activated", {
                "source_id": source_id,
                "controller": player_id,
                "ability_index": ability_index,
                "targets": list(targets),
                "stack_item_id": stack_item_id
            }))
            for target_id in targets:
                self.event_bus.publish(GameEvent("became_target", {
                    "target_id": target_id,
                    "source_id": source_id,
                    "controller": player_id
                }))

        return {"status": "SUCCESS", "action": "ACTIVATE_ABILITY", "stack_item_id": stack_item_id}

    def _validate_targets(self, player_id: str, definition: CardDefinition, targets: List[str], ability: bool = False) -> Tuple[bool, str]:
        if not all(isinstance(target, str) and target for target in targets):
            return False, "Targets must be non-empty string IDs."
        text = definition.text.lower()
        base_id = definition.base_id
        requires_target = "target" in text and base_id != "gravedigger"
        if requires_target and len(targets) != 1:
            return False, "This action requires exactly one target."
        if not requires_target and targets:
            return False, "This action does not take a target."
        if not targets:
            return True, ""

        target = targets[0]
        permanent = self.game_state.get_permanent(target)
        stack_entry = next((item for item in self.game_state.stack if item.get("stack_item_id") == target), None)
        in_own_graveyard = target in self.game_state.graveyards.get(player_id, [])

        if base_id in {"counterspell", "cancel", "mana_leak", "negate"}:
            if not stack_entry:
                return False, "The target must be a spell on the stack."
            if base_id == "negate":
                target_definition = self.catalog.get_definition(stack_entry.get("source", ""))
                if target_definition and target_definition.is_creature():
                    return False, "Negate cannot target a creature spell."
            return True, ""
        if base_id == "raise_dead":
            target_definition = self.catalog.get_definition(target)
            return (bool(in_own_graveyard and target_definition and target_definition.is_creature()), "Target must be your creature card in your graveyard.")
        if base_id in {"lava_spike", "mind_rot", "millstone"}:
            return (target in self.game_state.players, "Target must be a player.")
        if base_id in {"lightning_bolt", "shock", "searing_spear", "skullcrack", "rift_bolt", "incinerate", "healing_salve", "rod_of_ruin", "prodigal_sorcerer"}:
            if target not in self.game_state.players and not permanent:
                return False, "Target must be a player or permanent."
        elif not permanent:
            return False, "Target permanent is not on the battlefield."

        if permanent:
            target_definition = self.catalog.get_definition(target)
            if base_id in {"flame_slash", "unsummon", "giant_growth", "vines_of_vastwood", "swords_to_plowshares", "path_to_exile", "terror", "doom_blade", "pacifism", "royal_assassin", "mother_of_runes"} and not (target_definition and target_definition.is_creature()):
                return False, "Target must be a creature."
            if base_id == "naturalize" and target_definition and not ("Artifact" in target_definition.card_type or "Enchantment" in target_definition.card_type):
                return False, "Naturalize requires an artifact or enchantment target."
            if base_id in {"terror", "doom_blade"} and target_definition and target_definition.color == "B":
                return False, "This spell cannot target a black creature."
            if base_id == "terror" and target_definition and "Artifact" in target_definition.card_type:
                return False, "Terror cannot target an artifact creature."
            if base_id == "royal_assassin" and not permanent.get("tapped", False):
                return False, "Royal Assassin requires a tapped creature target."
            controller = self.game_state.get_permanent_controller(target)
            if base_id == "mother_of_runes" and controller != player_id:
                return False, "Mother of Runes must target a creature you control."
            if target_definition and "hexproof" in target_definition.keywords and controller != player_id:
                return False, "An opponent's hexproof permanent cannot be targeted."
            target_keywords = set(target_definition.keywords if target_definition else []) | set(permanent.get("keywords", []))
            if f"protection_from_{self._color_name(definition.color)}" in target_keywords:
                return False, "The target has protection from this source's color."
        return True, ""

    @staticmethod
    def _color_name(color: str) -> str:
        return {"W": "white", "U": "blue", "B": "black", "R": "red", "G": "green"}.get(color, "colorless")
