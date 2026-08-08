import threading
import time
from typing import Dict, Any, Optional
from app.client.state import ClientState
from app.client.transport import ClientTransport

def render_cli(state_dict: Dict[str, Any], local_pid: Optional[str]) -> None:
    print("\n" + "=" * 60)
    print(f"=== MTG GAME STATE (Turn {state_dict.get('turn', 1)}, Phase: {state_dict.get('phase', 'UNKNOWN')}) ===")
    print(f"Active Player: {state_dict.get('active_player', '?')} | Priority: {state_dict.get('priority_holder', '?')}")
    print("-" * 60)

    life_totals = state_dict.get("life_totals", {})
    lib_counts = state_dict.get("library_counts", {})
    hand_counts = state_dict.get("hand_counts", {})
    gy_dict = state_dict.get("graveyard", {})

    players = list(dict.fromkeys(list(life_totals.keys()) + list(lib_counts.keys())))
    if local_pid and local_pid not in players:
        players.insert(0, local_pid)
    
    opp_pid = next((p for p in players if p != local_pid), "opponent")
    my_pid = local_pid or "you"

    print(f"OPPONENT [{opp_pid}]: Life: {life_totals.get(opp_pid, 20)} | Library: {lib_counts.get(opp_pid, 0)} | Hand: {hand_counts.get(opp_pid, 0)} | GY: {len(gy_dict.get(opp_pid, []))}")
    
    bf_dict = state_dict.get("battlefield", {})
    opp_bf = bf_dict.get(opp_pid, [])
    if opp_bf:
        print("  Battlefield:")
        for card in opp_bf:
            status = "TAPPED" if card.get("tapped") else "UNTAPPED"
            stats = f" ({card.get('power', 0)}/{card.get('toughness', 0)})" if "power" in card else ""
            print(f"    - {card.get('id')}{stats} [{status}]")
    else:
        print("  Battlefield: (empty)")

    print("-" * 60)
    stack_list = state_dict.get("stack", [])
    if stack_list:
        print(f"STACK (Top -> Bottom):")
        for item in reversed(stack_list):
            print(f"  * [{item.get('controller')}] {item.get('source')} -> Targets: {item.get('targets', [])}")
    else:
        print("STACK: (empty)")
    print("-" * 60)

    print(f"YOU [{my_pid}]: Life: {life_totals.get(my_pid, 20)} | Library: {lib_counts.get(my_pid, 0)} | GY: {len(gy_dict.get(my_pid, []))}")
    my_bf = bf_dict.get(my_pid, [])
    if my_bf:
        print("  Battlefield:")
        for card in my_bf:
            status = "TAPPED" if card.get("tapped") else "UNTAPPED"
            stats = f" ({card.get('power', 0)}/{card.get('toughness', 0)})" if "power" in card else ""
            print(f"    - {card.get('id')}{stats} [{status}]")
    else:
        print("  Battlefield: (empty)")

    raw_hand = state_dict.get("hand", {})
    if isinstance(raw_hand, dict):
        my_hand = raw_hand.get(my_pid, [])
    elif isinstance(raw_hand, list):
        my_hand = raw_hand
    else:
        my_hand = []
    print(f"  Hand ({len(my_hand)}): {', '.join(my_hand) if my_hand else '(empty)'}")
    print("=" * 60 + "\n")

def player_setup():
    player_id = input("Enter Player ID: ").strip()
    print("Build your deck: ")

def run_cli(host: str = "127.0.0.1", port: int = 4444, verbose: bool = False, player_id: Optional[str] = None):
    player_id = (player_id or input("Enter Player ID: ")).strip()
    if not player_id:
        print("Player ID cannot be empty.")
        return
    t_obj = ClientTransport(verbose=verbose)
    state = ClientState(player_id=player_id)
    
    print(f"Connecting to MTGNP server at {host}:{port}...")
    try:
        t_obj.connect(host, port)
        t_obj.send_pdu(state.build_player_ready())
    except Exception as e:
        print(f"Failed to connect: {e}")
        t_obj.close()
        return

    def network_thread():
        while True:
            pdu = t_obj.read_pdu()
            if not pdu:
                print("Server disconnected.")
                break
            state.update_authoritative_state(pdu)
            ptype = pdu.get("type")
            if ptype == "GAME_STATE_UPDATE":
                if state.current_state.get("phase") == "LOBBY":
                    print(f"Lobby: {state.current_state.get('players_ready', 0)}/2 ready")
                else:
                    render_cli(state.current_state, state.player_id)
            elif ptype == "PRIORITY_GRANT":
                print(f"Priority: {pdu.get('player_id')}")
            elif ptype == "PHASE_TRANSITION":
                print(f"Phase: {pdu.get('to_phase')}")
            elif ptype == "ERROR":
                print(f"[SERVER ERROR {pdu.get('code')}]: {pdu.get('message')}")
            elif ptype == "GAME_OVER":
                print(f"[GAME OVER]: Winner: {pdu.get('winner_id')} ({pdu.get('reason')})")

    th = threading.Thread(target=network_thread, daemon=True)
    th.start()

    print("Commands: pass, land ID, cast ID [TARGET], keep [BOTTOM...], mulligan, discard IDs..., concede, ready, quit")
    while True:
        try:
            cmd = input("> ").strip()
            if cmd == "quit":
                break
            elif cmd == "pass":
                t_obj.send_pdu(state.build_priority_pass())
            elif cmd.startswith("land "):
                cid = cmd.split(" ", 1)[1]
                t_obj.send_pdu(state.build_play_land(cid))
            elif cmd.startswith("cast "):
                parts = cmd.split()
                card_id = parts[1]
                targets = parts[2:3]
                from app.shared.cards import CardCatalog
                definition = CardCatalog.get_instance().get_definition(card_id)
                payment = {
                    ("X" if color == "Generic" else color): amount
                    for color, amount in definition.mana_cost.items() if amount
                } if definition else {}
                t_obj.send_pdu(state.build_cast_spell(card_id, targets, payment))
            elif cmd == "mulligan":
                t_obj.send_pdu(state.build_mulligan_choice(False, []))
            elif cmd == "keep" or cmd.startswith("keep "):
                t_obj.send_pdu(state.build_mulligan_choice(True, cmd.split()[1:]))
            elif cmd.startswith("discard "):
                t_obj.send_pdu(state.build_discard(cmd.split()[1:]))
            elif cmd == "concede":
                t_obj.send_pdu(state.build_concede())
            elif cmd == "ready":
                state.reset_for_lobby()
                t_obj.send_pdu(state.build_player_ready())
            elif cmd == "ping":
                t_obj.send_pdu(state.build_ping(int(time.time() * 1000)))
        except (KeyboardInterrupt, EOFError):
            break
    t_obj.close()
