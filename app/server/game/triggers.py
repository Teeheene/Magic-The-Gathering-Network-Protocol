from typing import List, Dict, Any, Optional, Callable
from app.server.game.game_state import GameState
from app.server.game.stack import GameStack, StackItem
from app.server.game.events import GameEvent
from app.server.interfaces import TransportInterface, SeqNumProvider

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
    def __init__(self, game_state: GameState, stack: GameStack, transport: Optional[TransportInterface] = None, seq_num_provider: Optional[SeqNumProvider] = None):
        self.game_state = game_state
        self.stack = stack
        self.transport = transport
        self.seq_num_provider = seq_num_provider
        self.pending_triggers: List[TriggeredAbility] = []
        self._next_trg_id = 1

    def generate_trigger_id(self) -> str:
        tid = f"trg_{self._next_trg_id:02d}"
        self._next_trg_id += 1
        return tid

    def detect_triggers_for_event(self, event: GameEvent) -> List[TriggeredAbility]:
        detected: List[TriggeredAbility] = []
        # Check Goblin Guide attack trigger
        if event.event_type == "attacker_declared":
            attacker_id = event.data.get("creature_id")
            if attacker_id and "goblin_guide" in attacker_id:
                ctrl = self.game_state.get_permanent_controller(attacker_id) or self.game_state.active_player
                opp = self.game_state.get_opponent(ctrl)
                trg = TriggeredAbility(
                    trigger_id=self.generate_trigger_id(),
                    source_id=attacker_id,
                    controller=ctrl,
                    effect_summary="Defending player reveals top card of library. If land, put in hand.",
                    optional=False,
                    requires_target=False,
                    effect_fn=lambda item, state: self._goblin_guide_effect(opp, state)
                )
                detected.append(trg)

        # Check Phantasmal Bear target trigger
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
                    effect_fn=lambda item, state: self._phantasmal_bear_effect(target_id, state)
                )
                detected.append(trg)

        # Check Gray Merchant ETB trigger
        if event.event_type == "permanent_entered":
            card_id = event.data.get("card_id")
            if card_id and "gray_merchant" in card_id:
                ctrl = event.data.get("controller") or self.game_state.active_player
                trg = TriggeredAbility(
                    trigger_id=self.generate_trigger_id(),
                    source_id=card_id,
                    controller=ctrl,
                    effect_summary="You may gain life equal to your devotion to black.",
                    optional=True,
                    requires_target=False,
                    effect_fn=lambda item, state: self._gray_merchant_effect(ctrl, state)
                )
                detected.append(trg)

        self.pending_triggers.extend(detected)
        return detected

    def _goblin_guide_effect(self, opp: str, state: GameState) -> List[Dict[str, Any]]:
        lib = state.libraries.get(opp, [])
        if lib:
            top_card = lib[0]
            if "mountain" in top_card or "forest" in top_card or "plains" in top_card or "island" in top_card or "swamp" in top_card:
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
        devotion = sum(1 for p in state.battlefield.get(ctrl, []) if "swamp" in p.get("id", "") or "gray_merchant" in p.get("id", ""))
        devotion = max(1, devotion)
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

        # AP triggers placed first (bottom), NAP triggers placed on top (resolve first)
        ap_triggers = [t for t in self.pending_triggers if t.controller == ap]
        nap_triggers = [t for t in self.pending_triggers if t.controller == nap]
        
        self.pending_triggers.clear()

        # Place AP triggers
        for trg in ap_triggers:
            self._push_trigger_to_stack(trg)

        # Place NAP triggers (on top)
        for trg in nap_triggers:
            self._push_trigger_to_stack(trg)

    def _push_trigger_to_stack(self, trg: TriggeredAbility) -> None:
        stk_id = self.stack.generate_stack_item_id()
        item = StackItem(
            stack_item_id=stk_id,
            item_type="TRIGGER_ABILITY",
            source=trg.source_id,
            controller=trg.controller,
            targets=[],
            effect_fn=trg.effect_fn
        )
        self.stack.push(item)
