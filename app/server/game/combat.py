from typing import List, Dict, Any, Optional, Tuple, Set
from app.server.game.game_state import GameState
from app.server.game.cards import CardCatalog
from app.server.game.events import GameEvent
from app.server.interfaces import TransportInterface, SeqNumProvider

class CombatManager:
    def __init__(self, game_state: GameState, transport: Optional[TransportInterface] = None, seq_num_provider: Optional[SeqNumProvider] = None):
        self.game_state = game_state
        self.transport = transport
        self.seq_num_provider = seq_num_provider
        self.catalog = CardCatalog.get_instance()
        self.attackers: List[Dict[str, str]] = [] # [{"creature_id": "...", "target": "player_2"}]
        self.blockers: List[Dict[str, str]] = [] # [{"creature_id": "...", "blocking_id": "..."}]
        self.damage_orders: Dict[str, List[str]] = {} # attacker_id -> [blocker1, blocker2]

    def reset_combat(self) -> None:
        self.attackers.clear()
        self.blockers.clear()
        self.damage_orders.clear()

    def validate_and_declare_attackers(self, player_id: str, attacker_declarations: List[Dict[str, str]]) -> Tuple[bool, str]:
        if player_id != self.game_state.active_player:
            return False, "Only Active Player can declare attackers."

        if not attacker_declarations:
            self.reset_combat()
            return True, "No attackers declared."

        opponent = self.game_state.get_opponent(player_id)
        declared_ids: Set[str] = set()

        for decl in attacker_declarations:
            cid = decl.get("creature_id", "")
            target = decl.get("target", "")

            if cid in declared_ids:
                return False, f"Duplicate attacker declaration for {cid}."
            declared_ids.add(cid)

            if target != opponent:
                return False, f"Invalid target {target} for attacker. Must target opponent {opponent}."

            perm = self.game_state.get_permanent(cid)
            if not perm or self.game_state.get_permanent_controller(cid) != player_id:
                return False, f"You do not control creature {cid}."

            if perm.get("tapped", False):
                return False, f"Creature {cid} is tapped and cannot attack."

            if perm.get("summoning_sick", False):
                def_obj = self.catalog.get_definition(cid)
                if not def_obj or "haste" not in def_obj.keywords:
                    return False, f"Creature {cid} has summoning sickness."

            # Check defender / pacifism
            def_obj = self.catalog.get_definition(cid)
            if def_obj and "defender" in def_obj.keywords:
                return False, f"Creature {cid} has defender and cannot attack."

            if perm.get("attached_pacifism", False):
                return False, f"Creature {cid} is enchanted with Pacifism and cannot attack."

        # Apply attacker declaration
        self.attackers = list(attacker_declarations)
        for decl in attacker_declarations:
            cid = decl["creature_id"]
            perm = self.game_state.get_permanent(cid)
            def_obj = self.catalog.get_definition(cid)
            # Tap attacker unless vigilance
            if perm and (not def_obj or "vigilance" not in def_obj.keywords):
                perm["tapped"] = True

        return True, "Attackers declared successfully."

    def validate_and_declare_blockers(self, player_id: str, blocker_declarations: List[Dict[str, str]]) -> Tuple[bool, str]:
        if player_id == self.game_state.active_player:
            return False, "Active Player cannot declare blockers."

        if not blocker_declarations:
            self.blockers.clear()
            return True, "No blockers declared."

        attacking_ids = {a["creature_id"] for a in self.attackers}
        blocking_creature_ids: Set[str] = set()

        for decl in blocker_declarations:
            blocker_id = decl.get("creature_id", "")
            attacker_id = decl.get("blocking_id", "")

            if blocker_id in blocking_creature_ids:
                return False, f"Creature {blocker_id} cannot block multiple attackers."
            blocking_creature_ids.add(blocker_id)

            if attacker_id not in attacking_ids:
                return False, f"Target {attacker_id} is not an attacking creature."

            b_perm = self.game_state.get_permanent(blocker_id)
            if not b_perm or self.game_state.get_permanent_controller(blocker_id) != player_id:
                return False, f"You do not control blocker {blocker_id}."

            if b_perm.get("tapped", False):
                return False, f"Blocker {blocker_id} is tapped."

            if b_perm.get("attached_pacifism", False):
                return False, f"Blocker {blocker_id} is enchanted with Pacifism and cannot block."

            # Check flying restriction
            a_def = self.catalog.get_definition(attacker_id)
            b_def = self.catalog.get_definition(blocker_id)
            if a_def and "flying" in a_def.keywords:
                if not b_def or "flying" not in b_def.keywords:
                    return False, f"Creature {attacker_id} has flying; {blocker_id} cannot block it."

            # Check protection
            if a_def and b_def:
                if "protection_from_black" in a_def.keywords and b_def.color == "B":
                    return False, f"{attacker_id} has protection from black; {blocker_id} cannot block it."
                if "protection_from_white" in a_def.keywords and b_def.color == "W":
                    return False, f"{attacker_id} has protection from white; {blocker_id} cannot block it."

        self.blockers = list(blocker_declarations)
        return True, "Blockers declared successfully."

    def needs_damage_order(self) -> List[str]:
        # Return list of attacker_ids that have 2+ blockers
        blocker_counts: Dict[str, int] = {}
        for b in self.blockers:
            aid = b["blocking_id"]
            blocker_counts[aid] = blocker_counts.get(aid, 0) + 1
        return [aid for aid, cnt in blocker_counts.items() if cnt >= 2]

    def set_damage_order(self, attacker_id: str, blocker_order: List[str]) -> Tuple[bool, str]:
        assigned_blockers = [b["creature_id"] for b in self.blockers if b["blocking_id"] == attacker_id]
        if set(blocker_order) != set(assigned_blockers) or len(blocker_order) != len(assigned_blockers):
            return False, "Blocker order must contain each assigned blocker exactly once."
        self.damage_orders[attacker_id] = list(blocker_order)
        return True, "Damage order set successfully."

    def has_first_strike_or_double_strike(self) -> bool:
        all_combatants = [a["creature_id"] for a in self.attackers] + [b["creature_id"] for b in self.blockers]
        for cid in all_combatants:
            def_obj = self.catalog.get_definition(cid)
            if def_obj and ("first_strike" in def_obj.keywords or "double_strike" in def_obj.keywords):
                return True
        return False

    def resolve_combat_damage(self, is_first_strike_step: bool = False) -> Dict[str, Any]:
        damage_events: List[Dict[str, Any]] = []
        creatures_died: List[str] = []

        # Find attackers and their blockers
        for att in self.attackers:
            aid = att["creature_id"]
            target_player = att["target"]
            a_perm = self.game_state.get_permanent(aid)
            if not a_perm:
                continue

            a_def = self.catalog.get_definition(aid)
            a_power = a_perm.get("power", a_def.power if a_def else 0)
            a_fs = a_def and ("first_strike" in a_def.keywords or "double_strike" in a_def.keywords)
            a_ds = a_def and "double_strike" in a_def.keywords

            # Determine if attacker deals damage in this step
            if is_first_strike_step and not a_fs:
                pass
            elif not is_first_strike_step and a_fs and not a_ds:
                pass # Only dealt damage in first strike step
            else:
                # Get blockers for this attacker
                b_ids = [b["creature_id"] for b in self.blockers if b["blocking_id"] == aid]
                if not b_ids:
                    # Unblocked! Deals damage to defending player
                    if a_power > 0:
                        self.game_state.life_totals[target_player] -= a_power
                        damage_events.append({
                            "source": aid,
                            "target": target_player,
                            "amount": a_power
                        })
                else:
                    # Blocked! MTGNP 1.0 has NO trample. All damage assigned to blockers in damage order
                    ordered_blockers = self.damage_orders.get(aid, b_ids)
                    rem_damage = a_power
                    for bid in ordered_blockers:
                        if rem_damage <= 0:
                            break
                        b_perm = self.game_state.get_permanent(bid)
                        if b_perm:
                            b_def = self.catalog.get_definition(bid)
                            b_toughness = b_perm.get("toughness", b_def.toughness if b_def else 1)
                            b_current_damage = b_perm.get("damage", 0)
                            needed_lethal = max(1, b_toughness - b_current_damage)
                            assigned = min(rem_damage, needed_lethal) if len(ordered_blockers) > 1 else rem_damage
                            b_perm["damage"] = b_current_damage + assigned
                            rem_damage -= assigned
                            damage_events.append({
                                "source": aid,
                                "target": bid,
                                "amount": assigned
                            })

        # Blockers deal damage to attackers
        for blk in self.blockers:
            bid = blk["creature_id"]
            aid = blk["blocking_id"]
            b_perm = self.game_state.get_permanent(bid)
            a_perm = self.game_state.get_permanent(aid)
            if not b_perm or not a_perm:
                continue

            b_def = self.catalog.get_definition(bid)
            b_power = b_perm.get("power", b_def.power if b_def else 0)
            b_fs = b_def and ("first_strike" in b_def.keywords or "double_strike" in b_def.keywords)
            b_ds = b_def and "double_strike" in b_def.keywords

            if is_first_strike_step and not b_fs:
                continue
            if not is_first_strike_step and b_fs and not b_ds:
                continue

            if b_power > 0:
                a_perm["damage"] = a_perm.get("damage", 0) + b_power
                damage_events.append({
                    "source": bid,
                    "target": aid,
                    "amount": b_power
                })

        seq = self.seq_num_provider.next_seq_num() if self.seq_num_provider else 0
        pdu = {
            "type": "COMBAT_DAMAGE_RESULT",
            "seq_num": seq,
            "damage_events": damage_events,
            "life_totals": dict(self.game_state.life_totals),
            "creatures_died": creatures_died
        }

        if self.transport:
            self.transport.broadcast(pdu)

        return pdu
