from typing import Callable, Dict, Any, List, Optional
from app.server.game.game_state import GameState
from app.server.game.cards import CardCatalog
import app.server.game.effects as FX

def resolve_lightning_bolt(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.deal_damage(target, 3, item.source, state)

def resolve_shock(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.deal_damage(target, 2, item.source, state)

def resolve_lava_spike(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.deal_damage(target, 3, item.source, state)

def resolve_flame_slash(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.deal_damage(target, 4, item.source, state)

def resolve_searing_spear(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.deal_damage(target, 3, item.source, state)

def resolve_incinerate(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.deal_damage(target, 3, item.source, state)

def resolve_skullcrack(item: Any, state: GameState) -> List[Dict[str, Any]]:
    state.cant_gain_life = True
    state.cant_prevent_damage = True
    target = item.targets[0] if item.targets else ""
    changes = [{"change_type": "RULE_MOD", "effect": "CANT_GAIN_LIFE_OR_PREVENT_DAMAGE"}]
    changes.extend(FX.deal_damage(target, 3, item.source, state))
    return changes

def resolve_counterspell(item: Any, state: GameState, game_stack: Optional[Any] = None) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.counter_spell(target, state, game_stack)

def resolve_unsummon(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.return_to_hand(target, state)

def resolve_ponder(item: Any, state: GameState) -> List[Dict[str, Any]]:
    return FX.draw_cards(item.controller, 1, state)

def resolve_giant_growth(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.modify_power_toughness(target, 3, 3, "end_of_turn", state)

def resolve_naturalize(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.destroy_permanent(target, state)

def resolve_swords_to_plowshares(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    perm = state.get_permanent(target)
    power = perm.get("power", 0) if perm else 0
    controller = state.get_permanent_controller(target)
    changes = FX.exile_permanent(target, state)
    if controller:
        changes.extend(FX.gain_life(controller, power, state))
    return changes

def resolve_path_to_exile(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.exile_permanent(target, state)

def resolve_healing_salve(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    if target in state.players:
        return FX.gain_life(target, 3, state)
    else:
        return FX.prevent_damage(target, 3, state)

def resolve_terror(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.destroy_permanent(target, state)

def resolve_doom_blade(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.destroy_permanent(target, state)

def resolve_raise_dead(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.return_from_graveyard(target, item.controller, state)

def resolve_mind_rot(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    hand = state.hands.get(target, [])
    to_discard = hand[:2]
    return FX.discard_cards(target, to_discard, state)

def resolve_gray_merchant(item: Any, state: GameState) -> List[Dict[str, Any]]:
    perm = {"id": item.source, "tapped": False, "summoning_sick": True, "damage": 0}
    state.battlefield[item.controller].append(perm)
    return [{"change_type": "ENTER_BATTLEFIELD", "card_id": item.source, "controller": item.controller}]

def resolve_gravedigger(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.return_from_graveyard(target, item.controller, state)

def resolve_millstone(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.mill_cards(target, 2, state)

def resolve_rod_of_ruin(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.deal_damage(target, 1, item.source, state)

def resolve_prodigal_sorcerer(item: Any, state: GameState) -> List[Dict[str, Any]]:
    target = item.targets[0] if item.targets else ""
    return FX.deal_damage(target, 1, item.source, state)

def resolve_merfolk_looter(item: Any, state: GameState) -> List[Dict[str, Any]]:
    changes = FX.draw_cards(item.controller, 1, state)
    hand = state.hands.get(item.controller, [])
    if hand:
        changes.extend(FX.discard_cards(item.controller, [hand[-1]], state))
    return changes

def resolve_rampant_growth(item: Any, state: GameState) -> List[Dict[str, Any]]:
    return FX.search_library_and_put_on_battlefield(item.controller, "Land", True, state)

EFFECT_HANDLERS: Dict[str, Callable[[Any, GameState], List[Dict[str, Any]]]] = {
    "lightning_bolt": resolve_lightning_bolt,
    "shock": resolve_shock,
    "lava_spike": resolve_lava_spike,
    "flame_slash": resolve_flame_slash,
    "searing_spear": resolve_searing_spear,
    "incinerate": resolve_incinerate,
    "skullcrack": resolve_skullcrack,
    "rift_bolt": resolve_lightning_bolt,
    "counterspell": resolve_counterspell,
    "cancel": resolve_counterspell,
    "unsummon": resolve_unsummon,
    "ponder": resolve_ponder,
    "negate": resolve_counterspell,
    "mana_leak": resolve_counterspell,
    "giant_growth": resolve_giant_growth,
    "naturalize": resolve_naturalize,
    "vines_of_vastwood": resolve_giant_growth,
    "swords_to_plowshares": resolve_swords_to_plowshares,
    "path_to_exile": resolve_path_to_exile,
    "healing_salve": resolve_healing_salve,
    "terror": resolve_terror,
    "doom_blade": resolve_doom_blade,
    "raise_dead": resolve_raise_dead,
    "mind_rot": resolve_mind_rot,
    "gray_merchant": resolve_gray_merchant,
    "gravedigger": resolve_gravedigger,
    "millstone": resolve_millstone,
    "rod_of_ruin": resolve_rod_of_ruin,
    "prodigal_sorcerer": resolve_prodigal_sorcerer,
    "merfolk_looter": resolve_merfolk_looter,
    "rampant_growth": resolve_rampant_growth,
}

def get_effect_handler(base_id: str) -> Optional[Callable[[Any, GameState], List[Dict[str, Any]]]]:
    return EFFECT_HANDLERS.get(base_id)
