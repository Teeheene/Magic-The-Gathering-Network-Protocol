import re
import time

from app.client.deck_builder import CATALOG_PATH, choose_deck
from app.shared.card_catalog import CardCatalog


CARD_CATALOG = CardCatalog(CATALOG_PATH)

MAIN_PHASES = {"PRECOMBAT_MAIN", "POSTCOMBAT_MAIN"}
PRIORITY_PHASES = {
    "UPKEEP",
    "DRAW",
    "PRECOMBAT_MAIN",
    "BEGIN_COMBAT",
    "DECLARE_ATTACKERS",
    "DECLARE_BLOCKERS",
    "ASSIGN_DAMAGE_ORDER",
    "FIRST_STRIKE_DAMAGE",
    "END_OF_COMBAT",
    "POSTCOMBAT_MAIN",
    "END_STEP",
}
AUTOMATIC_PHASES = {"GAME_SETUP", "UNTAP", "COMBAT_DAMAGE"}


def card_id(card):
    return card.get("id") if isinstance(card, dict) else card


def playable_instants(state):
    return [
        current_card_id
        for current_card_id in state.local_hand
        if (
            (CARD_CATALOG.get_card_data(current_card_id) or {})
            .get("card_type", "")
            .casefold()
            == "instant"
        )
    ]


def playable_spells(state):
    return [
        current_card_id
        for current_card_id in state.local_hand
        if (
            (CARD_CATALOG.get_card_data(current_card_id) or {})
            .get("card_type", "")
            .casefold()
            != "land"
        )
    ]


def playable_lands(state):
    return [
        current_card_id
        for current_card_id in state.local_hand
        if (
            (CARD_CATALOG.get_card_data(current_card_id) or {})
            .get("card_type", "")
            .casefold()
            == "land"
        )
    ]


def non_mana_ability_sources(state):
    sources = []
    for permanent in state.battlefield.get(state.pid, []):
        source_id = card_id(permanent)
        card_data = CARD_CATALOG.get_card_data(source_id) or {}
        text = card_data.get("text", "")
        if ":" not in text:
            continue
        effect = text.split(":", 1)[1].strip().casefold()
        if effect.startswith("add {"):
            continue
        cost_text = text.split(":", 1)[0].casefold()
        if "tap" in cost_text and isinstance(permanent, dict):
            if permanent.get("tapped"):
                continue
            if (
                "creature" in card_data.get("card_type", "").casefold()
                and permanent.get("summoning_sick")
            ):
                continue
        sources.append(source_id)
    return sources


def display_valid_choices(title, card_ids):
    print(f"> {title}:")
    for current_card_id in card_ids:
        card_data = CARD_CATALOG.get_card_data(current_card_id) or {}
        name = card_data.get("name", current_card_id)
        text = card_data.get("text", "")
        print(f"  - {current_card_id}: {name} — {text}")


def mana_payment_for_card(card_id):
    card_data = CARD_CATALOG.get_card_data(card_id) or {}
    payment = {}
    for color, amount in card_data.get("mana_cost", {}).items():
        if not amount:
            continue
        payment["X" if color == "Generic" else color] = amount
    return payment


def ability_cost_payment(source_id):
    card_data = CARD_CATALOG.get_card_data(source_id) or {}
    text = card_data.get("text", "")
    cost_text = text.split(":", 1)[0] if ":" in text else ""
    mana = {}
    for symbol in re.findall(r"\{([^}]+)\}", cost_text):
        key = "X" if symbol.isdigit() else symbol
        amount = int(symbol) if symbol.isdigit() else 1
        mana[key] = mana.get(key, 0) + amount
    return {"tap": "tap" in cost_text.casefold(), "mana": mana}


def permanent_ids(state, predicate=None):
    result = []
    for permanents in state.battlefield.values():
        for permanent in permanents:
            current_id = card_id(permanent)
            if predicate is None or predicate(permanent, current_id):
                result.append(current_id)
    return result


def choose_targets(state, rules_text):
    text = rules_text.casefold()
    if "target" not in text:
        return []

    player_ids = list(state.life_totals)
    creature_ids = permanent_ids(
        state,
        lambda permanent, _: (
            isinstance(permanent, dict)
            and permanent.get("toughness") is not None
        ),
    )
    if "counter target" in text:
        legal_targets = [
            item.get("stack_item_id")
            for item in state.stack
            if item.get("stack_item_id")
        ]
    elif "any target" in text:
        legal_targets = player_ids + creature_ids
    elif "target player" in text:
        legal_targets = player_ids
    elif "target creature" in text:
        legal_targets = creature_ids
    else:
        legal_targets = player_ids + permanent_ids(state)

    if not legal_targets:
        print("> This spell or ability has no legal targets right now.")
        return None
    print("> Legal targets: " + ", ".join(legal_targets))
    target = input("> Target ID: ").strip()
    if target not in legal_targets:
        print("> Choose one of the listed targets.")
        return None
    return [target]

def wait_for_update(dispatcher, previous_seq_num):
    while dispatcher.connection.running:
        if dispatcher.state.last_error is not None:
            print(f"> Server error: {dispatcher.state.last_error['message']}")
            dispatcher.state.last_error = None
            return False
        if dispatcher.state.latest_seq_num != previous_seq_num:
            return True
        time.sleep(0.05)
    return False

def wait_for_phase(dispatcher, phase):
    observed_phase = None
    while dispatcher.connection.running:
        if dispatcher.state.last_error is not None:
            print(f"> Server error: {dispatcher.state.last_error['message']}")
            dispatcher.state.last_error = None
            return False
        current_phase = dispatcher.state.phase
        if current_phase != observed_phase:
            display_phase_status(current_phase)
            observed_phase = current_phase
        if current_phase == phase:
            return True
        time.sleep(0.05)
    return False


def display_phase_status(phase):
    messages = {
        "LOBBY": "Waiting in the lobby...",
        "GAME_SETUP": "Server is setting up the game...",
        "MULLIGAN": "Game setup complete. Starting mulligans...",
        "GAME_OVER": "The game has ended.",
    }
    message = messages.get(phase)
    if message is not None:
        print(f"> {message}")

def format_cards(cards):
    return ", ".join(str(card) for card in cards) if cards else "(empty)"

def display_game_state(state):
    width = 64
    player_ids = []
    for player_map in (
        state.life_totals,
        state.hand_counts,
        state.library_counts,
        state.battlefield,
        state.graveyard,
    ):
        for player_id in player_map:
            if player_id not in player_ids:
                player_ids.append(player_id)
    if state.pid not in player_ids:
        player_ids.insert(0, state.pid)

    priority_holder = (
        "YOU" if state.priority_holder == state.pid else state.priority_holder or "-"
    )

    print("\n" + "=" * width)
    print(f" MTG GAME | TURN {state.turn} | {state.phase}")
    print(f" Username: {state.pid}")
    print(f" Active player: {state.active_player or '-'}")
    print(f" Land played this turn: {state.land_played_this_turn}")
    print(f" Priority: {priority_holder}")
    print("-" * width)
    print(" PLAYERS")

    for player_id in player_ids:
        label = f"{player_id} (YOU)" if player_id == state.pid else player_id
        hand_count = state.hand_counts.get(player_id)
        if hand_count is None and player_id == state.pid:
            hand_count = len(state.local_hand)
        graveyard_count = len(state.graveyard.get(player_id, []))
        print(
            f" {label}: "
            f"Life {state.life_totals.get(player_id, '?')} | "
            f"Hand {hand_count if hand_count is not None else '?'} | "
            f"Deck {state.library_counts.get(player_id, '?')} | "
            f"Graveyard {graveyard_count}"
        )

    print("-" * width)
    print(f" YOUR HAND ({len(state.local_hand)})")
    if state.local_hand:
        for card_number, card_id in enumerate(state.local_hand, start=1):
            print(f" {card_number:>2}. {card_id}")
    else:
        print(" (empty)")

    print("-" * width)
    print(" BATTLEFIELD")
    for player_id in player_ids:
        print(f" {player_id}: {format_cards(state.battlefield.get(player_id, []))}")

    print("-" * width)
    print(" GRAVEYARD")
    for player_id in player_ids:
        print(f" {player_id}: {format_cards(state.graveyard.get(player_id, []))}")

    print("-" * width)
    print(f" STACK: {format_cards(state.stack)}")
    if state.attackers:
        print(f" ATTACKERS: {format_cards(state.attackers)}")
    if state.blockers:
        print(f" BLOCKERS: {format_cards(state.blockers)}")
    print("=" * width)


def choose_and_cast_spell(dispatcher, instant_only):
    valid_card_ids = (
        playable_instants(dispatcher.state)
        if instant_only
        else playable_spells(dispatcher.state)
    )
    if not valid_card_ids:
        spell_kind = "Instant cards" if instant_only else "spells"
        print(f"> You have no {spell_kind} available to cast.")
        return False
    title = "Instant cards you can cast" if instant_only else "Spells you can cast"
    display_valid_choices(title, valid_card_ids)
    card_id = input("> Card ID to cast: ").strip()
    if card_id not in valid_card_ids:
        print("> Choose one of the listed card IDs.")
        return False

    card_data = CARD_CATALOG.get_card_data(card_id) or {}
    targets = choose_targets(dispatcher.state, card_data.get("text", ""))
    if targets is None:
        return False
    dispatcher.state.last_error = None
    dispatcher.send_cast_spell(
        card_id,
        targets=targets,
        mana_payment=mana_payment_for_card(card_id),
    )
    return True


def cast_instant(dispatcher):
    return choose_and_cast_spell(dispatcher, instant_only=True)


def cast_main_phase_spell(dispatcher):
    return choose_and_cast_spell(dispatcher, instant_only=False)


def activate_non_mana_ability(dispatcher):
    valid_source_ids = non_mana_ability_sources(dispatcher.state)
    if not valid_source_ids:
        print("> You control no permanents with non-mana activated abilities.")
        return False
    display_valid_choices(
        "Permanents with non-mana activated abilities",
        valid_source_ids,
    )
    source_id = input("> Ability source ID: ").strip()
    if source_id not in valid_source_ids:
        print("> Choose one of the listed ability source IDs.")
        return False

    ability_index = input("> Ability index (default 0): ").strip()
    try:
        ability_index = int(ability_index or 0)
    except ValueError:
        print("> Ability index must be a number.")
        return False

    card_data = CARD_CATALOG.get_card_data(source_id) or {}
    targets = choose_targets(dispatcher.state, card_data.get("text", ""))
    if targets is None:
        return False
    dispatcher.state.last_error = None
    dispatcher.send_activate_ability(
        source_id,
        ability_index,
        targets=targets,
        cost_payment=ability_cost_payment(source_id),
    )
    return True


def pass_priority(dispatcher):
    dispatcher.state.last_error = None
    dispatcher.send_priority_pass()
    return True


def play_land(dispatcher):
    valid_card_ids = playable_lands(dispatcher.state)
    if not valid_card_ids:
        print("> You have no lands available to play.")
        return False
    display_valid_choices("Lands you can play", valid_card_ids)
    card_id = input("> Land card ID: ").strip()
    if card_id not in valid_card_ids:
        print("> Choose one of the listed land card IDs.")
        return False
    dispatcher.state.last_error = None
    dispatcher.send_play_land(card_id)
    return True


def declare_attackers(dispatcher):
    raw_attackers = input(
        "> Attackers as creature_id:target, separated by spaces "
        "(blank for none): "
    ).strip()
    attackers = []
    for declaration in raw_attackers.split():
        if ":" not in declaration:
            print("> Each attacker must use creature_id:target.")
            return False
        creature_id, target = declaration.split(":", 1)
        attackers.append({"creature_id": creature_id, "target": target})

    dispatcher.state.last_error = None
    dispatcher.send_declare_attackers(attackers)
    return True


def declare_blockers(dispatcher):
    raw_blockers = input(
        "> Blockers as creature_id:attacker_id, separated by spaces "
        "(blank for none): "
    ).strip()
    blockers = []
    for declaration in raw_blockers.split():
        if ":" not in declaration:
            print("> Each blocker must use creature_id:attacker_id.")
            return False
        creature_id, blocking_id = declaration.split(":", 1)
        blockers.append({
            "creature_id": creature_id,
            "blocking_id": blocking_id,
        })

    dispatcher.state.last_error = None
    dispatcher.send_declare_blockers(blockers)
    return True


def assign_damage_order(dispatcher):
    attacker_id = input("> Attacker ID: ").strip()
    if not attacker_id:
        print("> Attacker ID cannot be empty.")
        return False
    blocker_order = input("> Blocker IDs in damage order: ").strip().split()
    dispatcher.state.last_error = None
    dispatcher.send_assign_damage_order(attacker_id, blocker_order)
    return True


def discard_to_hand_limit(dispatcher):
    discard_count = max(0, len(dispatcher.state.local_hand) - 7)
    card_ids = input(
        f"> Discard {discard_count} card ID(s), separated by spaces: "
    ).strip().split()
    if len(card_ids) != discard_count:
        print(f"> Enter exactly {discard_count} card ID(s).")
        return False
    dispatcher.state.last_error = None
    dispatcher.send_discard(card_ids)
    return True


def has_sorcery_timing(state):
    return (
        state.phase in MAIN_PHASES
        and state.active_player == state.pid
        and state.priority_holder == state.pid
        and not state.stack
    )


def build_action_menu(state):
    if has_sorcery_timing(state):
        actions = [
            ("Cast a spell", cast_main_phase_spell),
            ("Activate a non-mana ability", activate_non_mana_ability),
        ]
        if not state.land_played_this_turn:
            actions.append(("Play a land", play_land))
        actions.append(("Pass priority", pass_priority))
        return actions

    return [
        ("Cast an instant", cast_instant),
        ("Activate a non-mana ability", activate_non_mana_ability),
        ("Pass priority", pass_priority),
    ]


def handle_game_action(dispatcher, choice, actions):
    try:
        action_index = int(choice) - 1
        if action_index < 0:
            raise IndexError
        _, action = actions[action_index]
    except (ValueError, IndexError):
        print("> Choose one of the listed actions.")
        return False
    return action(dispatcher)


def has_usable_priority(state):
    return (
        state.priority_holder == state.pid
        and state.priority_seq_num is not None
        and state.priority_seq_num is not None
    )


def handle_priority_phase(dispatcher, previous_seq_num):
    if dispatcher.state.priority_holder != dispatcher.state.pid:
        print("> Waiting for priority...")
        wait_for_update(dispatcher, previous_seq_num)
        return

    if not has_usable_priority(dispatcher.state):
        print("> Waiting for the server's priority grant...")
        wait_for_update(dispatcher, previous_seq_num)
        return

    actions = build_action_menu(dispatcher.state)
    print(f" {dispatcher.state.phase} ACTIONS")
    for action_number, (label, _) in enumerate(actions, start=1):
        print(f" {action_number}. {label}")

    choice = input("> Choice: ").strip()
    if handle_game_action(dispatcher, choice, actions):
        wait_for_update(dispatcher, previous_seq_num)


def handle_declare_attackers_phase(dispatcher, previous_seq_num):
    if dispatcher.state.attackers_declared:
        handle_priority_phase(dispatcher, previous_seq_num)
        return
    if dispatcher.state.active_player == dispatcher.state.pid:
        if declare_attackers(dispatcher):
            wait_for_update(dispatcher, previous_seq_num)
        return
    print("> Waiting for the active player to declare attackers...")
    wait_for_update(dispatcher, previous_seq_num)


def handle_declare_blockers_phase(dispatcher, previous_seq_num):
    if dispatcher.state.blockers_declared:
        handle_priority_phase(dispatcher, previous_seq_num)
        return
    if dispatcher.state.active_player != dispatcher.state.pid:
        if declare_blockers(dispatcher):
            wait_for_update(dispatcher, previous_seq_num)
        return
    print("> Waiting for the defending player to declare blockers...")
    wait_for_update(dispatcher, previous_seq_num)


def handle_damage_order_phase(dispatcher, previous_seq_num):
    if not dispatcher.state.pending_damage_orders:
        handle_priority_phase(dispatcher, previous_seq_num)
        return
    if dispatcher.state.active_player == dispatcher.state.pid:
        if assign_damage_order(dispatcher):
            wait_for_update(dispatcher, previous_seq_num)
        return
    print("> Waiting for combat damage order...")
    wait_for_update(dispatcher, previous_seq_num)


def handle_cleanup_phase(dispatcher, previous_seq_num):
    if (
        dispatcher.state.active_player == dispatcher.state.pid
        and len(dispatcher.state.local_hand) > 7
    ):
        if discard_to_hand_limit(dispatcher):
            wait_for_update(dispatcher, previous_seq_num)
        return
    print("> Waiting for cleanup to finish...")
    wait_for_update(dispatcher, previous_seq_num)


def handle_automatic_phase(dispatcher, previous_seq_num):
    print(f"> {dispatcher.state.phase} is handled automatically by the server...")
    wait_for_update(dispatcher, previous_seq_num)


def handle_card_choice(dispatcher, previous_seq_num):
    request = dispatcher.state.pending_card_choice or {}
    choice_type = request.get("choice_type")
    print(f"> {request.get('prompt', 'Card choice required')}")
    options = request.get("options", [])
    if options:
        print("> Options: " + ", ".join(str(option) for option in options))
    if choice_type == "SELECT_CARDS":
        response = {"selected_cards": input("> Card ID(s): ").strip().split()}
    elif choice_type == "SELECT_TARGETS":
        response = {"selected_targets": input("> Target ID: ").strip().split()}
    elif choice_type == "ORDER_CARDS":
        response = {"ordered_cards": input("> Top-to-bottom card IDs: ").strip().split()}
    elif choice_type == "YES_NO":
        response = {"answer": input("> Yes? [y/N]: ").strip().casefold() == "y"}
    elif choice_type == "COLOR":
        response = {"color": input("> Color: ").strip().upper()}
    elif choice_type in {"PAY_MANA", "MADNESS_CAST"}:
        pay = input("> Pay/cast? [y/N]: ").strip().casefold() == "y"
        response = {"pay" if choice_type == "PAY_MANA" else "cast": pay}
        if pay:
            response["mana_payment"] = dict(request.get("required_mana", {}))
    else:
        print("> Unsupported card choice type.")
        return
    dispatcher.send_card_choice_response(**response)
    wait_for_update(dispatcher, previous_seq_num)


def game_screen(dispatcher):
    while dispatcher.connection.running:
        if dispatcher.state.is_game_over:
            display_game_over(dispatcher.state)
            return
        if dispatcher.state.phase == "LOBBY":
            print("> Match ended because a player disconnected.")
            return

        display_game_state(dispatcher.state)
        phase = dispatcher.state.phase
        previous_seq_num = dispatcher.state.latest_seq_num

        if dispatcher.state.pending_card_choice is not None:
            handle_card_choice(dispatcher, previous_seq_num)
            continue

        if phase == "CLEANUP":
            handle_cleanup_phase(dispatcher, previous_seq_num)
            continue

        if phase == "DECLARE_ATTACKERS":
            handle_declare_attackers_phase(dispatcher, previous_seq_num)
            continue

        if phase == "DECLARE_BLOCKERS":
            handle_declare_blockers_phase(dispatcher, previous_seq_num)
            continue

        if phase == "ASSIGN_DAMAGE_ORDER":
            handle_damage_order_phase(dispatcher, previous_seq_num)
            continue

        if phase in AUTOMATIC_PHASES:
            handle_automatic_phase(dispatcher, previous_seq_num)
            continue

        if phase in PRIORITY_PHASES:
            handle_priority_phase(dispatcher, previous_seq_num)
            continue

        print(f"> Waiting for server handling of {phase}...")
        wait_for_update(dispatcher, previous_seq_num)


def display_game_over(state):
    result = state.game_over_info or {}
    winner_id = result.get("winner_id")
    loser_id = result.get("loser_id")
    reason = result.get("reason", "UNKNOWN")

    print("\n" + "=" * 64)
    print(" GAME OVER")
    print(f" Winner: {winner_id or '-'}")
    print(f" Loser: {loser_id or '-'}")
    print(f" Reason: {reason}")
    print("=" * 64)


def request_new_hand(dispatcher):
    previous_seq_num = dispatcher.state.latest_seq_num
    dispatcher.state.last_error = None
    dispatcher.send_mulligan_choice(False, [])
    return wait_for_update(dispatcher, previous_seq_num)


def choose_cards_to_bottom(mulligans_taken):
    if mulligans_taken == 0:
        return []

    while True:
        cards_to_bottom = input(
            f"> Enter {mulligans_taken} card ID(s) to bottom, "
            "separated by spaces: "
        ).strip().split()
        if len(cards_to_bottom) == mulligans_taken:
            return cards_to_bottom
        print(f"> Enter exactly {mulligans_taken} card ID(s).")


def keep_hand(dispatcher, mulligans_taken):
    cards_to_bottom = choose_cards_to_bottom(mulligans_taken)
    previous_seq_num = dispatcher.state.latest_seq_num
    dispatcher.state.last_error = None
    dispatcher.send_mulligan_choice(True, cards_to_bottom)

    if not wait_for_update(dispatcher, previous_seq_num):
        return False

    print("> Hand kept.")
    print("> Waiting for the other player to finish mulligans...")
    return wait_for_phase(dispatcher, "UPKEEP")


def mulligan_screen(dispatcher):
    print("\n==== MULLIGAN PHASE ====")
    print("Y = draw a new hand | N = keep this hand")

    mulligans_taken = 0
    while dispatcher.connection.running:
        if dispatcher.state.local_hand:
            print(f"> Your hand: {dispatcher.state.local_hand}")

        choice = input("> MULLIGAN (Y/N)? ").strip().casefold()
        if choice == "y":
            if not request_new_hand(dispatcher):
                continue
            mulligans_taken += 1
            print(
                "> New hand requested. When you keep, bottom "
                f"{mulligans_taken} card(s)."
            )
            continue

        if choice == "n":
            if keep_hand(dispatcher, mulligans_taken):
                return game_screen(dispatcher)
            continue

        print("> Please enter Y or N.")


def prompt_connection_setup(host, port):
    print("==== MTGP CLIENT ====")
    print(f"Connection Setup ({host}:{port})")
    return input("> Username: ").strip()


def prompt_deck_setup():
    print("Deck Setup")
    deck_list = choose_deck()
    print(f"> Deck ready: {len(deck_list)} cards")
    return deck_list


def prompt_join_lobby():
    print("\nType 'enter' to join the lobby")
    while True:
        if input("> ").strip().casefold() == "enter":
            return
        print("> Type 'enter' when you are ready.")


def show_connection_error(error):
    print(f"> Connection failed: {error}")


def show_returning_to_connection():
    print("\n> Returning to the connection screen...")


def ask_to_try_again():
    while True:
        choice = input("> Try connecting again? (Y/N): ").strip().casefold()
        if choice == "y":
            return True
        if choice == "n":
            return False
        print("> Please enter Y or N.")
