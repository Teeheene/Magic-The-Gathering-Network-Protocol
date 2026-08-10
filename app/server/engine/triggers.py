from typing import Any, Callable, Dict, List, Optional
from app.shared.card_catalog import CardCatalog


def get_base_id(card_id: str) -> str:
    return CardCatalog.base_card_id(card_id)



def calculate_devotion(controller_battlefield: List[Dict[str, Any]], color: str, catalog: CardCatalog) -> int:
    """Calculate devotion to a specific color across a player's battlefield permanents."""
    devotion = 0
    for perm in controller_battlefield:
        card_id = perm.get("id", "")
        base_id = get_base_id(card_id)
        data = catalog.get_card_data(base_id) if catalog else None
        if data and isinstance(data.get("mana_cost"), dict):
            devotion += data["mana_cost"].get(color, 0)
    return max(0, devotion)



class GameEvent:
    def __init__(self, event_type: str, data: Dict[str, Any]):
        self.event_type = event_type
        self.data = data


class EventBus:
    def __init__(self):
        self._subscribers: List[Callable[[GameEvent], None]] = []

    def subscribe(self, callback: Callable[[GameEvent], None]):
        self._subscribers.append(callback)

    def publish(self, event: GameEvent):
        for sub in list(self._subscribers):
            try:
                sub(event)
            except Exception as err:
                print(f"Error handling event {event.event_type}: {err}")


class TriggeredAbility:
    def __init__(
        self,
        trigger_id: str,
        source_id: str,
        controller: str,
        effect_summary: str,
        requires_target: bool = False,
        legal_targets: Optional[List[str]] = None,
        effect_fn: Optional[Callable[[Dict[str, Any], Any], Any]] = None,
        batch_id: Optional[str] = None,
    ):
        self.trigger_id = trigger_id
        self.source_id = source_id
        self.controller = controller
        self.effect_summary = effect_summary
        self.requires_target = requires_target
        self.legal_targets = legal_targets or []
        self.effect_fn = effect_fn
        self.batch_id = batch_id

    def to_dict(self) -> Dict[str, Any]:
        return {
            "trigger_id": self.trigger_id,
            "source_id": self.source_id,
            "controller": self.controller,
            "effect_summary": self.effect_summary,
            "requires_target": self.requires_target,
            "legal_targets": self.legal_targets,
            "batch_id": self.batch_id,
        }


class TriggerManager:
    def __init__(self, game_engine: Any, catalog: CardCatalog):
        self.game = game_engine
        self.catalog = catalog
        self.pending_triggers: List[TriggeredAbility] = []
        self._next_trg_id = 1
        self._next_batch_id = 1
        self.ordered_batches: set = set()

    def generate_trigger_id(self) -> str:
        tid = f"trg_{self._next_trg_id:02d}"
        self._next_trg_id += 1
        return tid

    def generate_batch_id(self) -> str:
        bid = f"batch_{self._next_batch_id:02d}"
        self._next_batch_id += 1
        return bid

    def detect_triggers_for_event(self, event: GameEvent) -> List[TriggeredAbility]:
        detected: List[TriggeredAbility] = []

        if event.event_type == "attacker_declared":
            attacker_id = event.data.get("creature_id", "")
            base_id = get_base_id(attacker_id)
            if base_id == "goblin_guide":
                ctrl = event.data.get("controller", "")
                ctrl_client = self.game.client_for_player(ctrl) if hasattr(self.game, "client_for_player") else None
                opp_client = self.game.other_client(ctrl_client) if (hasattr(self.game, "other_client") and ctrl_client) else None
                opp = opp_client.pid if opp_client else ""
                trg = TriggeredAbility(
                    trigger_id=self.generate_trigger_id(),
                    source_id=attacker_id,
                    controller=ctrl,
                    effect_summary="Defending player reveals top card of library. If land, put in hand.",
                    requires_target=False,
                    effect_fn=lambda item, game, opp_pid=opp: self._resolve_goblin_guide(opp_pid, game),
                )
                detected.append(trg)


        elif event.event_type == "became_target":
            target_id = event.data.get("target_id", "")
            base_id = get_base_id(target_id)
            if base_id == "phantasmal_bear":
                owner, perm = None, None
                if hasattr(self.game, "find_permanent"):
                    res = self.game.find_permanent(target_id)
                    if isinstance(res, (tuple, list)) and len(res) == 2:
                        owner, perm = res
                ctrl = owner.pid if (owner and getattr(owner, "pid", None)) else event.data.get("controller", "")
                trg = TriggeredAbility(
                    trigger_id=self.generate_trigger_id(),
                    source_id=target_id,
                    controller=ctrl,
                    effect_summary="Sacrifice Phantasmal Bear.",
                    requires_target=False,
                    effect_fn=lambda item, game: self._resolve_phantasmal_bear(target_id, game),
                )
                detected.append(trg)

        elif event.event_type == "spell_cast":
            caster = event.data.get("controller", "")
            card_id = event.data.get("card_id", "")
            data = self.catalog.get_card_data(get_base_id(card_id)) if self.catalog else None
            card_type = data.get("card_type", "").casefold() if data else ""
            if "creature" not in card_type:
                # Prowess check on battlefield
                ctrl_client = self.game.client_for_player(caster) if hasattr(self.game, "client_for_player") else None
                if ctrl_client:
                    for perm in list(ctrl_client.battlefield):
                        perm_id = perm.get("id", "")
                        if get_base_id(perm_id) == "monastery_swiftspear":
                            trg = TriggeredAbility(
                                trigger_id=self.generate_trigger_id(),
                                source_id=perm_id,
                                controller=caster,
                                effect_summary="Monastery Swiftspear gets +1/+1 until end of turn (Prowess).",
                                requires_target=False,
                                effect_fn=lambda item, game, p_id=perm_id: self._resolve_prowess(p_id, game),
                            )
                            detected.append(trg)

        elif event.event_type in ("creature_entered", "permanent_entered"):
            creature_id = event.data.get("creature_id", "") or event.data.get("card_id", "")
            ctrl = event.data.get("controller", "")
            base_id = CardCatalog.base_card_id(creature_id)

            if base_id == "gray_merchant":
                trg = TriggeredAbility(
                    trigger_id=self.generate_trigger_id(),
                    source_id=creature_id,
                    controller=ctrl,
                    effect_summary="Each opponent loses X life, you gain X life, where X is devotion to black.",
                    requires_target=False,
                    effect_fn=lambda item, game: self._resolve_gray_merchant(ctrl, game),
                )
                detected.append(trg)
            elif base_id == "goblin_bushwhacker" and event.data.get("kicked"):
                trg = TriggeredAbility(
                    trigger_id=self.generate_trigger_id(),
                    source_id=creature_id,
                    controller=ctrl,
                    effect_summary="Creatures you control get +1/+0 and gain haste until end of turn.",
                    requires_target=False,
                    effect_fn=lambda item, game: self._resolve_bushwhacker(ctrl, game),
                )
                detected.append(trg)
            elif base_id == "gravedigger":
                ctrl_client = self.game.client_for_player(ctrl) if hasattr(self.game, "client_for_player") else None
                gy = list(ctrl_client.graveyard) if ctrl_client else []
                creatures_in_gy = [c for c in gy if "creature" in (self.catalog.get_card_data(CardCatalog.base_card_id(c)) or {}).get("card_type", "").casefold()]
                if creatures_in_gy:
                    trg = TriggeredAbility(
                        trigger_id=self.generate_trigger_id(),
                        source_id=creature_id,
                        controller=ctrl,
                        effect_summary="Return target creature card from your graveyard to your hand.",
                        requires_target=True,
                        legal_targets=creatures_in_gy,
                        effect_fn=lambda item, game: self._resolve_gravedigger(ctrl, item, game),
                    )
                    detected.append(trg)

        return detected


    def _resolve_goblin_guide(self, defending_player: str, game: Any):
        def_client = game.client_for_player(defending_player)
        if def_client and def_client.library:
            top_card = def_client.library[0]
            base_id = CardCatalog.base_card_id(top_card)
            data = self.catalog.get_card_data(base_id) if self.catalog else None
            is_land = "land" in (data.get("card_type", "").casefold() if data else "")
            print(f"Goblin Guide revealed {top_card} (is_land={is_land})")
            if is_land:
                def_client.library.pop(0)
                def_client.hand.append(top_card)


    def _resolve_phantasmal_bear(self, bear_id: str, game: Any):
        owner, perm = game.find_permanent(bear_id) if hasattr(game, "find_permanent") else (None, None)
        if owner and perm and perm in owner.battlefield:
            owner.battlefield.remove(perm)
            owner.graveyard.append(bear_id)

    def _resolve_prowess(self, swiftspear_id: str, game: Any):
        owner, perm = game.find_permanent(swiftspear_id) if hasattr(game, "find_permanent") else (None, None)
        if perm:
            perm["temp_power_buff"] = perm.get("temp_power_buff", 0) + 1
            perm["temp_toughness_buff"] = perm.get("temp_toughness_buff", 0) + 1

    def _resolve_bushwhacker(self, controller: str, game: Any):
        ctrl_client = game.client_for_player(controller)
        if ctrl_client:
            for perm in ctrl_client.battlefield:
                data = game.card_data(perm.get("id", "")) or {}
                if "creature" in data.get("card_type", "").casefold():
                    perm["temp_power_buff"] = perm.get("temp_power_buff", 0) + 1
                    perm["temporary_haste"] = True

    def _resolve_gray_merchant(self, controller: str, game: Any):
        ctrl_client = game.client_for_player(controller) if hasattr(game, "client_for_player") else None
        if ctrl_client:
            devotion = calculate_devotion(ctrl_client.battlefield, "B", self.catalog)
            opp_client = game.other_client(ctrl_client) if hasattr(game, "other_client") else None
            if opp_client:
                opp_client.life_total -= devotion
            game.gain_life(ctrl_client, devotion)

    def _resolve_gravedigger(self, controller: str, item: Dict[str, Any], game: Any):
        target = item.get("target")
        ctrl_client = game.client_for_player(controller) if hasattr(game, "client_for_player") else None
        if ctrl_client and target in ctrl_client.graveyard:
            ctrl_client.graveyard.remove(target)
            ctrl_client.hand.append(target)
