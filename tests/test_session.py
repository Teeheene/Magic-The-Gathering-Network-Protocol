import random
import unittest

from app.server.game.session import GameSession
from app.server.network.server import Server


class FakePlayer:
    def __init__(self):
        self.player_id = None
        self.deck_list = []
        self.sent = []
        self.closed = False

    def send(self, pdu):
        self.sent.append(pdu)

    def close(self):
        self.closed = True


def make_session(deck_size=10):
    session = GameSession(rng=random.Random(7))
    alice = FakePlayer()
    bob = FakePlayer()
    alice_deck = [f"mountain_{index:03d}" for index in range(1, deck_size + 1)]
    bob_deck = [f"island_{index:03d}" for index in range(1, deck_size + 1)]
    assert session.add_player(alice, "alice", alice_deck)[0]
    assert session.add_player(bob, "bob", bob_deck)[0]
    session.start()
    return session, alice, bob, alice_deck, bob_deck


def keep_hand(session, player):
    player_id = player.player_id
    return session.handle_pdu(player, {
        "type": "MULLIGAN_CHOICE",
        "seq_num": session.state_seq_nums[player_id],
        "keep": True,
        "cards_to_bottom": [],
    })


class TestGameSetupAndMulligan(unittest.TestCase):
    def test_setup_shuffles_draws_seven_and_hides_opponent_hand(self):
        session, alice, bob, alice_deck, bob_deck = make_session()

        self.assertEqual(session.game_state.phase, "MULLIGAN")
        self.assertEqual(session.game_state.turn, 0)
        self.assertEqual(len(session.game_state.hands["alice"]), 7)
        self.assertEqual(len(session.game_state.libraries["alice"]), 3)
        self.assertCountEqual(session.game_state.hands["alice"] + session.game_state.libraries["alice"], alice_deck)
        alice_state = alice.sent[-1]["state"]
        self.assertEqual(set(alice_state["hand"]), {"alice"})
        self.assertNotIn("bob", alice_state["hand"])
        self.assertEqual(alice_state["hand_counts"]["bob"], 7)

    def test_london_mulligan_redraw_and_bottom_count_are_enforced(self):
        session, alice, bob, *_ = make_session()
        redraw = session.handle_pdu(alice, {
            "type": "MULLIGAN_CHOICE", "seq_num": session.state_seq_nums["alice"],
            "keep": False, "cards_to_bottom": [],
        })
        self.assertEqual(redraw["status"], "SUCCESS")
        self.assertEqual(session.mulligan_counts["alice"], 1)
        self.assertEqual(len(session.game_state.hands["alice"]), 7)

        before = list(session.game_state.hands["alice"])
        rejected = session.handle_pdu(alice, {
            "type": "MULLIGAN_CHOICE", "seq_num": session.state_seq_nums["alice"],
            "keep": True, "cards_to_bottom": [],
        })
        self.assertEqual(rejected["code"], "ILLEGAL_ACTION")
        self.assertEqual(session.game_state.hands["alice"], before)

        bottom = before[0]
        accepted = session.handle_pdu(alice, {
            "type": "MULLIGAN_CHOICE", "seq_num": session.state_seq_nums["alice"],
            "keep": True, "cards_to_bottom": [bottom],
        })
        self.assertEqual(accepted["status"], "SUCCESS")
        self.assertEqual(session.game_state.libraries["alice"][-1], bottom)

    def test_both_players_keep_starts_turn_at_untap_then_upkeep(self):
        session, alice, bob, *_ = make_session()
        keep_hand(session, alice)
        keep_hand(session, bob)

        self.assertEqual(session.game_state.turn, 1)
        self.assertEqual(session.game_state.phase, "UPKEEP")
        self.assertEqual(session.game_state.priority_holder, session.game_state.active_player)
        transitions = [p for p in alice.sent if p.get("type") == "PHASE_TRANSITION"]
        self.assertEqual([p["to_phase"] for p in transitions[-2:]], ["UNTAP", "UPKEEP"])


class TestPriorityAndErrors(unittest.TestCase):
    def setUp(self):
        self.session, self.alice, self.bob, *_ = make_session()
        keep_hand(self.session, self.alice)
        keep_hand(self.session, self.bob)

    def player(self, player_id):
        return self.alice if player_id == "alice" else self.bob

    def test_priority_pass_reaches_the_other_player(self):
        holder = self.session.game_state.priority_holder
        result = self.session.handle_pdu(self.player(holder), {
            "type": "PRIORITY_PASS",
            "seq_num": self.session.priority_manager.current_priority_seq_num,
        })
        opponent = self.session.game_state.get_opponent(holder)
        self.assertEqual(result["status"], "PASSED")
        self.assertEqual(self.session.game_state.priority_holder, opponent)
        self.assertEqual(self.player(opponent).sent[-2]["type"], "PRIORITY_GRANT")

    def test_stale_action_is_atomic_and_reissues_same_priority_token(self):
        holder = self.session.game_state.priority_holder
        player = self.player(holder)
        token = self.session.priority_manager.current_priority_seq_num
        before = self.session.game_state.get_personalized_state(holder)
        result = self.session.handle_pdu(player, {
            "type": "PRIORITY_PASS", "seq_num": token + 99,
        })
        self.assertEqual(result["code"], "STALE_ACTION")
        self.assertEqual(result["rejected_action"]["type"], "PRIORITY_PASS")
        self.assertEqual(player.sent[-1]["type"], "PRIORITY_GRANT")
        self.assertEqual(player.sent[-1]["seq_num"], token)
        self.assertEqual(self.session.game_state.get_personalized_state(holder), before)

    def test_unknown_type_uses_normative_error_code(self):
        result = self.session.handle_pdu(self.alice, {"type": "DANCE", "seq_num": 1})
        self.assertEqual(result["code"], "UNKNOWN_TYPE")

    def test_concede_uses_latest_server_sequence_and_ends_game(self):
        latest = self.session.last_sent_seq_nums["alice"]
        result = self.session.handle_pdu(self.alice, {
            "type": "CONCEDE", "seq_num": latest, "player_id": "alice",
        })
        self.assertEqual(result["reason"], "CONCEDE")
        self.assertEqual(result["winner_id"], "bob")
        self.assertFalse(self.session.running)

    def test_lethal_stack_resolution_returns_game_over_without_dispatch_crash(self):
        self.session.game_state.life_totals["bob"] = 2
        self.session.game_state.hands["alice"].append("shock_001")
        self.session.game_state.battlefield["alice"].append({"id": "mountain_001", "tapped": False})
        self.session.priority_manager.grant_priority("alice")
        cast_result = self.session.handle_pdu(self.alice, {
            "type": "CAST_SPELL",
            "seq_num": self.session.priority_manager.current_priority_seq_num,
            "card_id": "shock_001", "targets": ["bob"], "mana_payment": {"R": 1},
        })
        self.assertEqual(cast_result["status"], "SUCCESS")
        self.session.handle_pdu(self.alice, {
            "type": "PRIORITY_PASS", "seq_num": self.session.priority_manager.current_priority_seq_num,
        })
        result = self.session.handle_pdu(self.bob, {
            "type": "PRIORITY_PASS", "seq_num": self.session.priority_manager.current_priority_seq_num,
        })
        self.assertEqual(result["type"], "GAME_OVER")
        self.assertEqual(result["reason"], "LIFE_ZERO")

    def pass_window(self):
        for _ in range(2):
            holder = self.session.game_state.priority_holder
            self.session.handle_pdu(self.player(holder), {
                "type": "PRIORITY_PASS",
                "seq_num": self.session.priority_manager.current_priority_seq_num,
            })

    def test_full_empty_combat_turn_uses_normative_phase_order(self):
        self.pass_window()  # upkeep -> draw
        self.assertEqual(self.session.game_state.phase, "DRAW")
        self.pass_window()  # draw -> precombat main
        self.pass_window()  # precombat main -> begin combat
        self.pass_window()  # begin combat -> declare attackers
        self.assertEqual(self.session.game_state.phase, "DECLARE_ATTACKERS")

        active = self.session.game_state.active_player
        self.session.handle_pdu(self.player(active), {
            "type": "DECLARE_ATTACKERS", "seq_num": self.session.current_phase_seq_num,
            "attackers": [],
        })
        self.assertEqual(self.session.game_state.phase, "END_OF_COMBAT")
        self.pass_window()  # end combat -> postcombat main
        self.pass_window()  # postcombat main -> end step
        self.pass_window()  # end step -> cleanup -> next untap/upkeep

        self.assertEqual(self.session.game_state.turn, 2)
        self.assertEqual(self.session.game_state.phase, "UPKEEP")
        transitions = [
            pdu["to_phase"] for pdu in self.alice.sent
            if pdu.get("type") == "PHASE_TRANSITION"
        ]
        self.assertIn("CLEANUP", transitions)
        self.assertEqual(transitions[-2:], ["UNTAP", "UPKEEP"])

    def test_draw_from_empty_library_ends_game(self):
        active = self.session.game_state.active_player
        self.session.game_state.turn = 2
        self.session.game_state.phase = "UPKEEP"
        self.session.game_state.libraries[active].clear()
        self.session.priority_manager.open_priority_window()
        self.pass_window()
        self.assertFalse(self.session.running)
        self.assertEqual(self.player(active).sent[-1]["type"], "GAME_OVER")
        self.assertEqual(self.player(active).sent[-1]["reason"], "DECK_EMPTY")

    def test_cleanup_waits_for_valid_discard(self):
        active = self.session.game_state.active_player
        player = self.player(active)
        self.session.game_state.phase = "END_STEP"
        self.session.game_state.hands[active] = [f"mountain_{index:03d}" for index in range(1, 9)]
        self.session.priority_manager.open_priority_window()
        self.pass_window()
        self.assertEqual(self.session.game_state.phase, "CLEANUP")
        self.assertEqual(self.session.game_state.turn, 1)

        token = self.session.state_seq_nums[active]
        card = self.session.game_state.hands[active][0]
        result = self.session.handle_pdu(player, {
            "type": "DISCARD", "seq_num": token, "card_ids": [card],
        })
        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(self.session.game_state.turn, 2)
        self.assertIn(card, self.session.game_state.graveyards[active])


class TestLobbyValidation(unittest.TestCase):
    def setUp(self):
        self.server = Server.__new__(Server)
        self.server.players = []
        self.server.seq_num = 0

    def test_duplicate_id_and_illegal_deck_do_not_close_connection(self):
        alice = FakePlayer()
        bob = FakePlayer()
        self.server.players = [alice, bob]
        self.assertTrue(self.server._accept_player_ready(alice, {
            "type": "PLAYER_READY", "seq_num": 1, "player_id": "Alice", "deck_list": ["mountain_001"],
        }))
        self.assertFalse(self.server._accept_player_ready(bob, {
            "type": "PLAYER_READY", "seq_num": 1, "player_id": "alice", "deck_list": ["island_001"],
        }))
        self.assertEqual(bob.sent[-1]["code"], "DUPLICATE_ID")
        self.assertFalse(bob.closed)

        self.assertFalse(self.server._accept_player_ready(bob, {
            "type": "PLAYER_READY", "seq_num": 2, "player_id": "bob", "deck_list": [],
        }))
        self.assertEqual(bob.sent[-1]["code"], "ILLEGAL_DECK")
        self.assertFalse(bob.closed)

    def test_lobby_submission_can_be_replaced(self):
        alice = FakePlayer()
        bob = FakePlayer()
        self.server.players = [alice, bob]
        self.assertTrue(self.server._accept_player_ready(alice, {
            "type": "PLAYER_READY", "seq_num": 1, "player_id": "alice", "deck_list": ["mountain_001"],
        }))
        self.assertTrue(self.server._accept_player_ready(alice, {
            "type": "PLAYER_READY", "seq_num": 2, "player_id": "alice2", "deck_list": ["forest_001"],
        }))
        self.assertEqual(alice.player_id, "alice2")
        self.assertEqual(alice.deck_list, ["forest_001"])


if __name__ == "__main__":
    unittest.main()
