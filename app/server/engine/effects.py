from typing import Any, Dict, List, Optional, Tuple


class CardEffects:
    @classmethod
    def resolve_card_effect(
        cls, base_id: str, source_id: str, targets: List[str], controller_client: Any, opponent_client: Any, game: Any
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """
        Resolve individual card spell effects for the 58 fixed card set.
        Returns (resolution_status, list_of_state_changes).
        """
        changes: List[Dict[str, Any]] = []

        target_id = targets[0] if targets else None

        # Burn spells
        burn_amounts = {
            "lightning_bolt": 3,
            "shock": 2,
            "lava_spike": 3,
            "flame_slash": 4,
            "searing_spear": 3,
            "skullcrack": 3,
            "rift_bolt": 3,
            "incinerate": 3,
        }
        if base_id in burn_amounts:
            amount = burn_amounts[base_id]
            if target_id == opponent_client.pid or target_id == controller_client.pid:
                target_c = opponent_client if target_id == opponent_client.pid else controller_client
                target_c.life_total -= amount
                changes.append({"type": "DAMAGE_PLAYER", "target": target_id, "amount": amount})
            else:
                owner, perm = game.find_permanent(target_id) if hasattr(game, "find_permanent") else (None, None)
                if perm and isinstance(perm, dict):
                    perm["damage"] = perm.get("damage", 0) + amount
                    changes.append({"type": "DAMAGE_CREATURE", "target": target_id, "amount": amount})

            if base_id == "skullcrack":
                game.cant_gain_life_this_turn = True
            if base_id == "incinerate" and target_id and not (target_id == opponent_client.pid or target_id == controller_client.pid):
                owner, perm = game.find_permanent(target_id) if hasattr(game, "find_permanent") else (None, None)
                if perm:
                    perm["cant_regenerate"] = True

            return "RESOLVED", changes

        # Counterspells
        if base_id in {"counterspell", "cancel", "negate", "mana_leak"}:
            if not target_id:
                return "FIZZLE", []
            target_item = next((item for item in game.stack if item.get("stack_item_id") == target_id), None)
            if not target_item:
                return "FIZZLE", []

            if base_id == "mana_leak":
                # Check if target controller can pay {3}
                # For simplified execution: if controller has >= 3 untapped lands, pay {3}, else counter
                target_ctrl = game.client_for_player(target_item.get("controller"))
                untapped_lands = [p for p in target_ctrl.battlefield if "land" in (game.card_data(p.get("id", "")).get("card_type", "").casefold()) and not p.get("tapped")]
                if len(untapped_lands) >= 3:
                    # Pay 3 lands
                    for l in untapped_lands[:3]:
                        l["tapped"] = True
                    return "PAID_MANA_LEAK", [{"type": "PAY_MANA", "player": target_ctrl.pid, "amount": 3}]

            # Remove from stack
            game.stack.remove(target_item)
            if target_item.get("item_type") == "SPELL":
                target_source = target_item.get("source")
                target_ctrl = game.client_for_player(target_item.get("controller"))
                if target_ctrl and target_source:
                    target_ctrl.graveyard.append(target_source)
            changes.append({"type": "COUNTER_SPELL", "stack_item_id": target_id})
            return "RESOLVED", changes

        # Unsummon
        if base_id == "unsummon":
            owner, perm = game.find_permanent(target_id) if hasattr(game, "find_permanent") else (None, None)
            if owner and perm:
                owner.battlefield.remove(perm)
                owner.hand.append(target_id)
                changes.append({"type": "BOUNCE_CREATURE", "target": target_id, "owner": owner.pid})
                return "RESOLVED", changes

        # Giant Growth
        if base_id == "giant_growth":
            owner, perm = game.find_permanent(target_id) if hasattr(game, "find_permanent") else (None, None)
            if perm:
                perm["temp_power_buff"] = perm.get("temp_power_buff", 0) + 3
                perm["temp_toughness_buff"] = perm.get("temp_toughness_buff", 0) + 3
                changes.append({"type": "TEMP_BUFF", "target": target_id, "power": 3, "toughness": 3})
                return "RESOLVED", changes

        # Dark Ritual
        if base_id == "dark_ritual":
            controller_client.mana_pool = getattr(controller_client, "mana_pool", {})
            controller_client.mana_pool["B"] = controller_client.mana_pool.get("B", 0) + 3
            changes.append({"type": "ADD_MANA", "player": controller_client.pid, "mana": {"B": 3}})
            return "RESOLVED", changes

        if base_id == "raise_dead":
            if target_id in controller_client.graveyard:
                controller_client.graveyard.remove(target_id)
                controller_client.hand.append(target_id)
                changes.append({"type": "RETURN_TO_HAND", "target": target_id})
                return "RESOLVED", changes
            return "FIZZLE", []

        # Ponder
        if base_id == "ponder":
            if controller_client.library:
                drawn = controller_client.library.pop(0)
                controller_client.hand.append(drawn)
                changes.append({"type": "DRAW_CARD", "player": controller_client.pid, "card_id": drawn})
            return "RESOLVED", changes

        # Destroy spells (Terror, Doom Blade, Naturalize)
        if base_id in {"terror", "doom_blade", "naturalize"}:
            change = game.destroy_permanent(
                target_id,
                allow_regeneration=base_id != "terror",
            )
            if change:
                changes.append(change)
                return "RESOLVED", changes

        return "RESOLVED", changes

    @classmethod
    def resolve_ability_effect(
        cls, base_id: str, source_id: str, targets: List[str], controller_client: Any, opponent_client: Any, game: Any
    ) -> Tuple[str, List[Dict[str, Any]]]:
        changes: List[Dict[str, Any]] = []
        target_id = targets[0] if targets else None

        if base_id in {"prodigal_sorcerer", "rod_of_ruin"}:
            if target_id == opponent_client.pid or target_id == controller_client.pid:
                target_c = opponent_client if target_id == opponent_client.pid else controller_client
                target_c.life_total -= 1
                changes.append({"type": "DAMAGE_PLAYER", "target": target_id, "amount": 1})
            else:
                owner, perm = game.find_permanent(target_id) if hasattr(game, "find_permanent") else (None, None)
                if perm and isinstance(perm, dict):
                    perm["damage"] = perm.get("damage", 0) + 1
                    changes.append({"type": "DAMAGE_CREATURE", "target": target_id, "amount": 1})
            return "RESOLVED", changes

        if base_id == "royal_assassin":
            owner, perm = game.find_permanent(target_id) if hasattr(game, "find_permanent") else (None, None)
            if owner and perm and isinstance(perm, dict) and perm.get("tapped"):
                change = game.destroy_permanent(target_id)
                changes.append(change)
                return "RESOLVED", changes
            return "FIZZLE", []

        if base_id == "troll_ascetic":
            owner, permanent = game.find_permanent(source_id)
            if owner is controller_client and isinstance(permanent, dict):
                permanent["regeneration_shield"] = True
                return "RESOLVED", [{"type": "REGENERATION_SHIELD", "target": source_id}]
            return "FIZZLE", []

        if base_id == "millstone":
            target_c = game.client_for_player(target_id) if (target_id and hasattr(game, "client_for_player")) else None
            if not target_c and opponent_client and target_id == opponent_client.pid:
                target_c = opponent_client
            if not target_c and controller_client and target_id == controller_client.pid:
                target_c = controller_client
            if target_c:
                milled = []
                for _ in range(2):
                    if target_c.library:
                        card = target_c.library.pop(0)
                        target_c.graveyard.append(card)
                        milled.append(card)
                changes.append({"type": "MILL", "target": target_c.pid, "cards": milled})
                return "RESOLVED", changes
            return "FIZZLE", []

        return "RESOLVED", changes

