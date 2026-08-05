import threading
import sys
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

    players = list(set(list(life_totals.keys()) + list(lib_counts.keys())))
    if not players:
        players = ["player_1", "player_2"]
    
    opp_pid = next((p for p in players if p != local_pid), "player_2")
    my_pid = local_pid or "player_1"

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

def run_cli(host: str = "127.0.0.1", port: int = 4444, verbose: bool = False, player_id: Optional[str] = None):
    t_obj = ClientTransport(verbose=verbose)
    state = ClientState(player_id=player_id)
    
    print(f"Connecting to MTGNP server at {host}:{port}...")
    try:
        t_obj.connect(host, port)
    except Exception as e:
        print(f"Failed to connect: {e}")
        return

    def network_thread():
        while True:
            pdu = t_obj.read_pdu()
            if not pdu:
                print("Server disconnected.")
                break
            state.update_authoritative_state(pdu)
            ptype = pdu.get("type")
            if ptype == "MATCH_START":
                print(f"Match Started! Assigned Player ID: {state.player_id}")
            elif ptype == "GAME_STATE_UPDATE":
                render_cli(state.current_state, state.player_id)
            elif ptype == "ERROR":
                print(f"[SERVER ERROR]: {pdu.get('message')}")
            elif ptype == "GAME_OVER":
                print(f"[GAME OVER]: Winner: {pdu.get('winner')}")

    th = threading.Thread(target=network_thread, daemon=True)
    th.start()

    print("CLI Client Ready. Type commands or 'pass', 'land <id>', 'quit':")
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
            elif cmd == "ready":
                t_obj.send_pdu(state.build_player_ready())
        except (KeyboardInterrupt, EOFError):
            break
    t_obj.close()
