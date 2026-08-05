from typing import List, Dict, Any, Optional, Callable
from app.server.game.game_state import GameState
from app.server.game.stack import GameStack, StackItem
from app.server.game.events import GameEvent, EventBus
from app.server.interfaces import TransportInterface, SeqNumProvider

def calculate_devotion_to_black(ctrl: str, state: GameState) -> int:
    try:
        from app.shared.cards import CardCatalog
        cat = CardCatalog.get_instance()
    except Exception:
        cat = None
        
    devotion = 0
    for perm in state.battlefield.get(ctrl, []):
        cid = perm.get("id", "")
        def_obj = cat.get_definition(cid) if cat else None
        if def_obj and hasattr(def_obj, "mana_cost") and isinstance(def_obj.mana_cost, dict):
            devotion += def_obj.mana_cost.get("B", 0)
    return max(0, devotion)

class TriggeredAbility:
    def __init__(self, trigger_id: str, source_id: str, controller: str, effect_summary: str, optional: bool = False, requires_target: bool = False, legal_targets: Optional[List[str]] = None, effect_fn: Optional[Callable] = None):
        self.trigger_id = trigger_id
        self.source_id = source_id
        self.controller = controller
        self.effect_summary = effect_summary
        self.optional = optional
        self.requires_target = requires_target
        self.legal_targets = legal_targets or []
        self.effect_fn = effect_fn

class TriggerManager:
    def __init__(self, game_state: GameState, stack: GameStack, transport: Optional[TransportInterface] = None, seq_num_provider: Optional[SeqNumProvider] = None, event_bus: Optional[EventBus] = None):
        self.game_state = game_state
        self.stack = stack
        self.transport = transport
        self.seq_num_provider = seq_num_provider
        self.event_bus = event_bus
        self.pending_triggers: List[TriggeredAbility] = []
        self._next_trg_id = 1

        if self.event_bus:
            self.event_bus.subscribe_all(self.on_event)

    def generate_trigger_id(self) -> str:
        tid = f"trg_{self._next_trg_id:02d}"
        self._next_trg_id += 1
        return tid

    def on_event(self, event: GameEvent) -> List[TriggeredAbility]:
        return self.detect_triggers_for_event(event)

    def detect_triggers_for_event(self, event: GameEvent) -> List[TriggeredAbility]:
        detected: List[TriggeredAbility] = []
        
        if event.event_type == "attacker_declared":
            attacker_id = event.data.get("creature_id")
            if attacker_id and "goblin_guide" in attacker_id:
                ctrl = event.data.get("controller") or self.game_state.get_permanent_controller(attacker_id) or self.game_state.active_player
                opp = event.data.get("defending_player") or self.game_state.get_opponent(ctrl)
                trg = TriggeredAbility(
                    trigger_id=self.generate_trigger_id(),
                    source_id=attacker_id,
                    controller=ctrl,
                    effect_summary="Defending player reveals top card of library. If land, put in hand.",
                    optional=False,
                    requires_target=False,
                    effect_fn=lambda item, state, stack=None: self._goblin_guide_effect(opp, state)
                )
                detected.append(trg)

        if event.event_type == "became_target":
            target_id = event.data.get("target_id")
            if target_id and "phantasmal_bear" in target_id:
                ctrl = self.game_state.get_permanent_controller(target_id) or ""
                trg = TriggeredAbility(
                    trigger_id=self.generate_trigger_id(),
                    source_id=target_id,
                    controller=ctrl,
                    effect_summary="Sacrifice Phantasmal Bear.",
                    optional=False,
                    requires_target=False,
                    effect_fn=lambda item, state, stack=None: self._phantasmal_bear_effect(target_id, state)
                )
                detected.append(trg)

        if event.event_type in ("permanent_entered", "permanent_entered_battlefield"):
            card_id = event.data.get("card_id") or event.data.get("permanent_id")
            if card_id and "gray_merchant" in card_id:
                ctrl = event.data.get("controller") or self.game_state.get_permanent_controller(card_id) or self.game_state.active_player
                trg = TriggeredAbility(
                    trigger_id=self.generate_trigger_id(),
                    source_id=card_id,
                    controller=ctrl,
                    effect_summary="Gray Merchant ETB: Each opponent loses life equal to your devotion to black. You gain life equal to life lost.",
                    optional=False,
                    requires_target=False,
                    effect_fn=lambda item, state, stack=None: self._gray_merchant_effect(ctrl, state)
                )
                detected.append(trg)

        self.pending_triggers.extend(detected)
        return detected

    def _goblin_guide_effect(self, opp: str, state: GameState) -> List[Dict[str, Any]]:
        lib = state.libraries.get(opp, [])
        if lib:
            top_card = lib[0]
            if any(l in top_card for l in ("mountain", "forest", "plains", "island", "swamp")):
                lib.pop(0)
                state.hands[opp].append(top_card)
                return [{"change_type": "REVEAL_LAND_TO_HAND", "player": opp, "card_id": top_card}]
        return [{"change_type": "REVEAL_CARD", "player": opp}]

    def _phantasmal_bear_effect(self, bear_id: str, state: GameState) -> List[Dict[str, Any]]:
        for ctrl in state.players:
            perms = state.battlefield[ctrl]
            for idx, perm in enumerate(list(perms)):
                if perm.get("id") == bear_id:
                    perms.pop(idx)
                    state.graveyards[ctrl].append(bear_id)
                    return [{"change_type": "SACRIFICE", "target": bear_id}]
        return []

    def _gray_merchant_effect(self, ctrl: str, state: GameState) -> List[Dict[str, Any]]:
        devotion = calculate_devotion_to_black(ctrl, state)
        opp = state.get_opponent(ctrl)
        state.life_totals[opp] -= devotion
        state.life_totals[ctrl] += devotion
        return [
            {"change_type": "LIFE_LOSS", "target": opp, "amount": devotion},
            {"change_type": "LIFE_GAIN", "target": ctrl, "amount": devotion}
        ]

    def place_pending_triggers_on_stack(self, ap: str, nap: str) -> None:
        if not self.pending_triggers:
            return

        ap_triggers = [t for t in self.pending_triggers if t.controller == ap]
        nap_triggers = [t for t in self.pending_triggers if t.controller == nap]
        
        self.pending_triggers.clear()

        # AP triggers placed first (bottom of stack)
        for trg in ap_triggers:
            if not trg.optional and not trg.requires_target:
                self._push_trigger_to_stack(trg)
            else:
                self.pending_triggers.append(trg)

        # NAP triggers placed second (top of stack, resolves first)
        for trg in nap_triggers:
            if not trg.optional and not trg.requires_target:
                self._push_trigger_to_stack(trg)
            else:
                self.pending_triggers.append(trg)

    def _push_trigger_to_stack(self, trg: TriggeredAbility, chosen_target: Optional[str] = None) -> None:
        stk_id = self.stack.generate_stack_item_id()
        targets = [chosen_target] if chosen_target else []
        item = StackItem(
            stack_item_id=stk_id,
            item_type="TRIGGER_ABILITY",
            source=trg.source_id,
            controller=trg.controller,
            targets=targets,
            effect_fn=trg.effect_fn
        )
        self.stack.push(item)

    def handle_trigger_order_response(self, player_id: str, ordered_trigger_ids: List[str]) -> bool:
        player_pending = [t for t in self.pending_triggers if t.controller == player_id]
        expected_ids = {t.trigger_id for t in player_pending}
        if set(ordered_trigger_ids) != expected_ids or len(ordered_trigger_ids) != len(player_pending):
            return False
        
        trg_map = {t.trigger_id: t for t in player_pending}
        for tid in ordered_trigger_ids:
            trg = trg_map[tid]
            self._push_trigger_to_stack(trg)
            self.pending_triggers.remove(trg)
        return True

    def handle_trigger_choice_response(self, player_id: str, trigger_id: str, accept: bool, chosen_target: Optional[str] = None) -> bool:
        trg = next((t for t in self.pending_triggers if t.trigger_id == trigger_id and t.controller == player_id), None)
        if not trg:
            return False
        
        self.pending_triggers.remove(trg)
        if accept:
            if trg.requires_target:
                if not chosen_target or chosen_target not in trg.legal_targets:
                    return False
            self._push_trigger_to_stack(trg, chosen_target)
        return True
