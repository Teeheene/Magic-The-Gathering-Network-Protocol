from typing import List, Dict, Any, Optional, Tuple
from app.server.game.game_state import GameState
from app.server.game.events import GameEvent

class StateBasedActions:
    @classmethod
    def check_and_apply(cls, game_state: GameState) -> Tuple[List[Dict[str, Any]], List[GameEvent], Optional[Dict[str, Any]]]:
        all_sba_changes: List[Dict[str, Any]] = []
        generated_events: List[GameEvent] = []
        game_over_result: Optional[Dict[str, Any]] = None

        while True:
            changes_this_pass: List[Dict[str, Any]] = []
            
            # 1. Check zero or less life
            p1 = game_state.players[0] if len(game_state.players) > 0 else ""
            p2 = game_state.players[1] if len(game_state.players) > 1 else ""

            p1_dead = game_state.life_totals.get(p1, 20) <= 0
            p2_dead = game_state.life_totals.get(p2, 20) <= 0

            if p1_dead or p2_dead:
                if p1_dead and p2_dead:
                    # Simultaneous zero life: Active Player loses, Non-Active Player wins (RFC 8.4)
                    loser = game_state.active_player
                    winner = game_state.get_opponent(loser)
                elif p1_dead:
                    loser = p1
                    winner = p2
                else:
                    loser = p2
                    winner = p1

                game_over_result = {
                    "winner_id": winner,
                    "loser_id": loser,
                    "reason": "LIFE_ZERO"
                }
                break # Game over!

            # 2. Check creature toughness <= 0 & lethal damage >= toughness
            for player in list(game_state.players):
                perms = game_state.battlefield[player]
                for idx, perm in enumerate(list(perms)):
                    if "power" in perm: # Creature
                        toughness = perm.get("toughness", 0)
                        damage = perm.get("damage", 0)
                        cid = perm.get("id", "")

                        if toughness <= 0 or damage >= toughness:
                            perms.pop(idx)
                            game_state.graveyards[player].append(cid)
                            change = {
                                "change_type": "CREATURE_DIED",
                                "target": cid,
                                "controller": player,
                                "reason": "ZERO_TOUGHNESS" if toughness <= 0 else "LETHAL_DAMAGE"
                            }
                            changes_this_pass.append(change)
                            generated_events.append(GameEvent("creature_died", {"card_id": cid, "controller": player}))
                            break # Re-check stabilization loop

            if not changes_this_pass:
                break # Stabilized! No further SBA changes in this pass

            all_sba_changes.extend(changes_this_pass)

        return all_sba_changes, generated_events, game_over_result
