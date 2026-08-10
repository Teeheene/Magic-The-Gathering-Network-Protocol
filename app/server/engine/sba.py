from typing import Any, Dict, List, Optional, Tuple


class StateBasedActions:
    @classmethod
    def check_and_apply(cls, game_state: Any) -> Tuple[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
        """
        State-Based Actions (SBA) Check Loop per MTG Rules & RFC §8:
        1. Check life total <= 0 for all players (simultaneous 0 life: Active Player loses, Non-Active Player wins).
        2. Check empty library draw (deckout).
        3. Check creature toughness <= 0 or damage >= toughness -> move creature to graveyard.
        4. Repeat until no new changes occur.
        """
        changes: List[Dict[str, Any]] = []
        game_over_info: Optional[Dict[str, Any]] = None

        while True:
            pass_changes = 0

            # 1. Decked players check
            decked = getattr(game_state, "decked_players", set())
            if isinstance(decked, (set, list, tuple)) and decked:
                loser = game_state.active_player if game_state.active_player in decked else next(iter(decked))
                winner = game_state.other_player(loser) if hasattr(game_state, "other_player") else "opponent"
                game_over_info = {
                    "winner_id": winner,
                    "loser_id": loser,
                    "reason": "DECK_EMPTY",
                }
                break


            # 2. Life totals check
            clients = getattr(game_state, "clients", [])
            if len(clients) >= 2:
                p1, p2 = clients[0], clients[1]
                p1_dead = getattr(p1, "life_total", 20) <= 0
                p2_dead = getattr(p2, "life_total", 20) <= 0

                if p1_dead or p2_dead:
                    if p1_dead and p2_dead:
                        # Simultaneous zero life: Active Player loses (RFC §8.4)
                        loser = game_state.active_player
                        winner = p1.pid if p2.pid == loser else p2.pid
                    elif p1_dead:
                        loser, winner = p1.pid, p2.pid
                    else:
                        loser, winner = p2.pid, p1.pid

                    game_over_info = {
                        "winner_id": winner,
                        "loser_id": loser,
                        "reason": "LIFE_ZERO",
                    }
                    break

            # 3. Creature lethal damage / toughness <= 0 check
            for client in clients:
                for perm in list(getattr(client, "battlefield", [])):
                    if isinstance(perm, dict):
                        toughness = perm.get("toughness")
                        damage = perm.get("damage", 0)
                        if toughness is not None and (toughness <= 0 or damage >= toughness):
                            if (
                                toughness > 0
                                and perm.get("regeneration_shield")
                                and not perm.get("cant_regenerate")
                            ):
                                perm["regeneration_shield"] = False
                                perm["tapped"] = True
                                perm["damage"] = 0
                                changes.append({
                                    "type": "REGENERATE",
                                    "card_id": perm.get("id", ""),
                                    "owner": client.pid,
                                })
                                pass_changes += 1
                                continue
                            client.battlefield.remove(perm)
                            cid = perm.get("id", "")
                            client.graveyard.append(cid)
                            changes.append({"type": "CREATURE_DIED", "card_id": cid, "owner": client.pid})
                            pass_changes += 1

            # 4. Auras whose attached permanent left the battlefield go to graveyard.
            for client in clients:
                for permanent in list(getattr(client, "battlefield", [])):
                    if not isinstance(permanent, dict) or not permanent.get("attached_to"):
                        continue
                    if game_state.find_permanent(permanent["attached_to"])[1] is None:
                        client.battlefield.remove(permanent)
                        card_id = permanent.get("id", "")
                        client.graveyard.append(card_id)
                        changes.append({"type": "AURA_DIED", "card_id": card_id, "owner": client.pid})
                        pass_changes += 1

            if pass_changes == 0:
                break

        return changes, game_over_info
