from typing import List, Dict, Any, Optional
from app.server.game.game_state import GameState
from app.server.game.cards import CardCatalog

def deal_damage(target: str, amount: int, source: str, game_state: GameState) -> List[Dict[str, Any]]:
    changes: List[Dict[str, Any]] = []
    if amount <= 0:
        return changes

    # Check damage prevention
    if not game_state.cant_prevent_damage and target in game_state.damage_prevention_shields:
        shield = game_state.damage_prevention_shields[target]
        prevented = min(shield, amount)
        amount -= prevented
        game_state.damage_prevention_shields[target] -= prevented

    if amount <= 0:
        return changes

    if target in game_state.players:
        game_state.life_totals[target] -= amount
        changes.append({
            "change_type": "DAMAGE",
            "target": target,
            "amount": amount,
            "source": source
        })
    else:
        perm = game_state.get_permanent(target)
        if perm:
            perm["damage"] = perm.get("damage", 0) + amount
            changes.append({
                "change_type": "DAMAGE",
                "target": target,
                "amount": amount,
                "source": source
            })
    return changes

def gain_life(player_id: str, amount: int, game_state: GameState) -> List[Dict[str, Any]]:
    if game_state.cant_gain_life or amount <= 0:
        return []
    game_state.life_totals[player_id] += amount
    return [{
        "change_type": "LIFE_GAIN",
        "target": player_id,
        "amount": amount
    }]

def lose_life(player_id: str, amount: int, game_state: GameState) -> List[Dict[str, Any]]:
    if amount <= 0:
        return []
    game_state.life_totals[player_id] -= amount
    return [{
        "change_type": "LIFE_LOSS",
        "target": player_id,
        "amount": amount
    }]

def draw_cards(player_id: str, count: int, game_state: GameState) -> List[Dict[str, Any]]:
    changes: List[Dict[str, Any]] = []
    lib = game_state.libraries.get(player_id, [])
    hand = game_state.hands.get(player_id, [])
    
    for _ in range(count):
        if lib:
            card = lib.pop(0)
            hand.append(card)
            changes.append({
                "change_type": "CARD_DRAWN",
                "player": player_id,
                "card_id": card
            })
        else:
            changes.append({
                "change_type": "DRAW_FROM_EMPTY_LIBRARY",
                "player": player_id
            })
            break
    return changes

def discard_cards(player_id: str, card_ids: List[str], game_state: GameState) -> List[Dict[str, Any]]:
    changes: List[Dict[str, Any]] = []
    hand = game_state.hands.get(player_id, [])
    gy = game_state.graveyards.get(player_id, [])
    
    for cid in list(card_ids):
        if cid in hand:
            hand.remove(cid)
            gy.append(cid)
            changes.append({
                "change_type": "DISCARD",
                "player": player_id,
                "card_id": cid
            })
    return changes

def counter_spell(target_stack_item_id: str, game_state: GameState, game_stack: Any) -> List[Dict[str, Any]]:
    if not game_stack or not hasattr(game_stack, "remove_item"):
        raise ValueError("counter_spell requires an authoritative GameStack instance.")
    removed_item = game_stack.remove_item(target_stack_item_id)
    if removed_item is None:
        return []
    source_card_id = removed_item.source
    controller = removed_item.controller
    gy = game_state.graveyards.get(controller, [])
    if source_card_id and source_card_id not in gy:
        gy.append(source_card_id)
    return [{
        "change_type": "COUNTER",
        "target": target_stack_item_id,
        "card_id": source_card_id
    }]

def destroy_permanent(permanent_id: str, game_state: GameState) -> List[Dict[str, Any]]:
    for controller in game_state.players:
        perms = game_state.battlefield[controller]
        for idx, perm in enumerate(list(perms)):
            if perm.get("id") == permanent_id:
                perms.pop(idx)
                game_state.graveyards[controller].append(permanent_id)
                return [{
                    "change_type": "DESTROY",
                    "target": permanent_id,
                    "controller": controller
                }]
    return []

def exile_permanent(permanent_id: str, game_state: GameState) -> List[Dict[str, Any]]:
    for controller in game_state.players:
        perms = game_state.battlefield[controller]
        for idx, perm in enumerate(list(perms)):
            if perm.get("id") == permanent_id:
                perms.pop(idx)
                game_state.exile[controller].append(permanent_id)
                return [{
                    "change_type": "EXILE",
                    "target": permanent_id,
                    "controller": controller
                }]
    return []

def return_to_hand(permanent_id: str, game_state: GameState) -> List[Dict[str, Any]]:
    for controller in game_state.players:
        perms = game_state.battlefield[controller]
        for idx, perm in enumerate(list(perms)):
            if perm.get("id") == permanent_id:
                perms.pop(idx)
                game_state.hands[controller].append(permanent_id)
                return [{
                    "change_type": "BOUNCE",
                    "target": permanent_id,
                    "owner": controller
                }]
    return []

def return_from_graveyard(card_id: str, player_id: str, game_state: GameState) -> List[Dict[str, Any]]:
    gy = game_state.graveyards.get(player_id, [])
    if card_id in gy:
        gy.remove(card_id)
        game_state.hands[player_id].append(card_id)
        return [{
            "change_type": "GRAVEYARD_TO_HAND",
            "player": player_id,
            "card_id": card_id
        }]
    return []

def modify_power_toughness(permanent_id: str, power_mod: int, toughness_mod: int, duration: str, game_state: GameState) -> List[Dict[str, Any]]:
    perm = game_state.get_permanent(permanent_id)
    if perm and "power" in perm:
        perm["power"] = max(0, perm["power"] + power_mod)
        perm["toughness"] = perm["toughness"] + toughness_mod
        if duration == "end_of_turn":
            game_state.temporary_effects.append({
                "type": "PT_MOD",
                "target": permanent_id,
                "power_mod": power_mod,
                "toughness_mod": toughness_mod
            })
        return [{
            "change_type": "MODIFY_PT",
            "target": permanent_id,
            "power_mod": power_mod,
            "toughness_mod": toughness_mod
        }]
    return []

def grant_keyword(permanent_id: str, keyword: str, duration: str, game_state: GameState) -> List[Dict[str, Any]]:
    perm = game_state.get_permanent(permanent_id)
    if perm:
        kw_list = perm.setdefault("keywords", [])
        if keyword not in kw_list:
            kw_list.append(keyword)
            if duration == "end_of_turn":
                game_state.temporary_effects.append({
                    "type": "KEYWORD",
                    "target": permanent_id,
                    "keyword": keyword
                })
            return [{
                "change_type": "GRANT_KEYWORD",
                "target": permanent_id,
                "keyword": keyword
            }]
    return []

def prevent_damage(target: str, amount: int, game_state: GameState) -> List[Dict[str, Any]]:
    game_state.damage_prevention_shields[target] = game_state.damage_prevention_shields.get(target, 0) + amount
    return [{
        "change_type": "PREVENT_DAMAGE_SHIELD",
        "target": target,
        "amount": amount
    }]

def search_library_and_put_on_battlefield(player_id: str, card_type: str, tapped: bool, game_state: GameState) -> List[Dict[str, Any]]:
    catalog = CardCatalog.get_instance()
    lib = game_state.libraries.get(player_id, [])
    found_id = None
    for cid in list(lib):
        def_obj = catalog.get_definition(cid)
        if def_obj and card_type in def_obj.card_type:
            found_id = cid
            break
    if found_id:
        lib.remove(found_id)
        perm = {"id": found_id, "tapped": tapped}
        game_state.battlefield[player_id].append(perm)
        return [{
            "change_type": "SEARCH_LAND_TO_BATTLEFIELD",
            "player": player_id,
            "card_id": found_id,
            "tapped": tapped
        }]
    return []

def mill_cards(player_id: str, count: int, game_state: GameState) -> List[Dict[str, Any]]:
    lib = game_state.libraries.get(player_id, [])
    gy = game_state.graveyards.get(player_id, [])
    milled = []
    for _ in range(count):
        if lib:
            card = lib.pop(0)
            gy.append(card)
            milled.append(card)
    if milled:
        return [{
            "change_type": "MILL",
            "player": player_id,
            "cards": milled
        }]
    return []
