import unittest
from unittest.mock import MagicMock

from app.client.pdu_dispatcher import PduDispatcher as ClientDispatcher
from app.client.state import ClientState
from app.server.connected_client import ConnectedClient
from app.server.game import Game


class CardChoiceFixture(unittest.TestCase):
    def setUp(self):
        connection = MagicMock()
        connection.clients = []
        connection.max_clients = 2
        connection.seq_num = 0
        self.game = Game(connection)
        self.alice = self.make_client("alice", 1001)
        self.bob = self.make_client("bob", 1002)
        connection.clients[:] = [self.alice, self.bob]
        self.game.clients = connection.clients
        self.game.active_player = "alice"
        self.game.priority_holder = "alice"
        self.game.phase = "PRECOMBAT_MAIN"

    @staticmethod
    def make_client(pid, port):
        client = ConnectedClient(MagicMock(), ("127.0.0.1", port))
        client.pid = pid
        client.hand = []
        client.library = []
        client.battlefield = []
        client.graveyard = []
        client.exile = []
        client.life_total = 20
        client.mana_pool = {}
        client.active_priority_seq_num = 10
        return client

    def request(self, continuation=None):
        return self.game.pdu_dispatcher.send_card_choice_request(
            self.alice, "test_source_001", "SELECT_CARDS", "Choose one",
            min_choices=1, max_choices=1, options=["a", "b"],
            validator=lambda pdu: pdu.get("selected_cards")
            if pdu.get("selected_cards") in (["a"], ["b"]) else None,
            continuation=continuation,
        )

    def resolve_item(self, source, controller="alice", targets=None, item_type="SPELL"):
        self.game.stack.append({
            "stack_item_id": 99, "item_type": item_type, "source": source,
            "controller": controller, "targets": list(targets or []),
        })
        return self.game.resolve_top_stack_item()

    def resolve_mode_item(self, source, mode, targets):
        self.game.stack.append({
            "stack_item_id": 98, "item_type": "SPELL", "source": source,
            "controller": "alice", "targets": list(targets), "mode": mode,
        })
        return self.game.resolve_top_stack_item()

    def answer(self, client, **fields):
        return self.game.pdu_dispatcher.handle(client, {
            "type": "CARD_CHOICE_RESPONSE",
            "seq_num": client.active_card_choice_seq_num,
            "player_id": client.pid,
            **fields,
        })

    def test_client_tracks_independent_choice_token_and_builds_response(self):
        state = ClientState("alice")
        connection = MagicMock()
        dispatcher = ClientDispatcher(state, connection)
        dispatcher.handle({
            "type": "CARD_CHOICE_REQUEST", "seq_num": 50, "player_id": "alice",
            "source_card_id": "x", "choice_type": "YES_NO", "prompt": "?",
            "min_choices": 1, "max_choices": 1, "options": [True, False],
        })
        self.assertEqual(state.card_choice_seq_num, 50)
        self.assertEqual(state.last_received_pdu_seq_num, 50)
        dispatcher.send_card_choice_response(answer=True)
        connection.send.assert_called_with({
            "type": "CARD_CHOICE_RESPONSE", "seq_num": 50,
            "player_id": "alice", "answer": True,
        })

    def test_invalid_response_keeps_original_token_and_corrected_resumes_once(self):
        calls = []
        request = self.request(lambda value: calls.append(value) or True)
        self.assertIsNone(self.game.priority_holder)
        self.assertFalse(self.game.pdu_dispatcher.handle(self.alice, {
            "type": "CARD_CHOICE_RESPONSE", "seq_num": request["seq_num"],
            "player_id": "alice", "selected_cards": ["z"],
        }))
        self.assertEqual(self.alice.active_card_choice_seq_num, request["seq_num"])
        self.assertIsNotNone(self.alice.pending_card_choice)
        self.assertTrue(self.game.pdu_dispatcher.handle(self.alice, {
            "type": "CARD_CHOICE_RESPONSE", "seq_num": request["seq_num"],
            "player_id": "alice", "selected_cards": ["a"],
        }))
        self.assertEqual(calls, [["a"]])
        self.assertIsNone(self.alice.pending_card_choice)

    def test_opponent_cannot_answer_and_gameplay_is_blocked(self):
        request = self.request()
        self.assertFalse(self.game.pdu_dispatcher.handle(self.bob, {
            "type": "CARD_CHOICE_RESPONSE", "seq_num": request["seq_num"],
            "player_id": "bob", "selected_cards": ["a"],
        }))
        self.assertFalse(self.game.pdu_dispatcher.handle(self.alice, {
            "type": "PRIORITY_PASS", "seq_num": 10,
        }))

    def test_ping_allowed_while_choice_pending(self):
        self.request()
        self.assertIsNotNone(self.game.pdu_dispatcher.handle(self.alice, {
            "type": "PING", "seq_num": 7, "timestamp": 1,
        }))

    def test_merfolk_looter_draws_then_privately_selects_discard(self):
        self.alice.hand = ["shock_001"]
        self.alice.library = ["island_001"]
        self.resolve_item("merfolk_looter_001", item_type="ABILITY")
        self.assertEqual(self.alice.pending_card_choice["options"], ["shock_001", "island_001"])
        self.assertFalse(any(b"CARD_CHOICE_REQUEST" in call.args[0] for call in self.bob.sock.sendall.call_args_list))
        self.assertTrue(self.answer(self.alice, selected_cards=["island_001"]))
        self.assertEqual(self.alice.hand, ["shock_001"])
        self.assertEqual(self.alice.graveyard, ["island_001"])

    def test_mind_rot_target_selects_exact_available_count(self):
        self.bob.hand = ["island_001", "shock_001", "forest_001"]
        self.resolve_item("mind_rot_001", targets=["bob"])
        self.assertEqual(self.bob.pending_card_choice["min_choices"], 2)
        self.assertFalse(self.answer(self.bob, selected_cards=["island_001", "island_001"]))
        self.assertTrue(self.answer(self.bob, selected_cards=["island_001", "shock_001"]))
        self.assertEqual(self.bob.hand, ["forest_001"])
        self.assertIn("mind_rot_001", self.alice.graveyard)

    def test_mother_color_choice_and_cleanup(self):
        target = {"id": "grizzly_bears_001", "keywords": []}
        self.alice.battlefield = [target]
        self.resolve_item("mother_of_runes_001", targets=[target["id"]], item_type="ABILITY")
        self.assertFalse(self.answer(self.alice, color="PURPLE"))
        self.answer(self.alice, color="BLACK")
        self.assertIn("protection from black", self.game.permanent_keywords(target))
        self.game.finish_cleanup()
        self.assertNotIn("protection from black", self.game.permanent_keywords(target))

    def test_rampant_growth_selects_basic_tapped_and_shuffles(self):
        self.alice.library = ["shock_001", "forest_001", "island_001"]
        self.resolve_item("rampant_growth_001")
        self.assertEqual(set(self.alice.pending_card_choice["options"]), {"forest_001", "island_001"})
        self.assertTrue(self.answer(self.alice, selected_cards=["forest_001"]))
        self.assertIn({"id": "forest_001", "tapped": True}, self.alice.battlefield)
        self.assertNotIn("forest_001", self.alice.library)

    def test_path_exiles_then_affected_controller_may_search(self):
        creature = {"id": "grizzly_bears_001", "keywords": []}
        self.bob.battlefield = [creature]
        self.bob.library = ["island_001", "shock_001"]
        self.resolve_item("path_to_exile_001", targets=[creature["id"]])
        self.assertIn(creature["id"], self.bob.exile)
        self.assertEqual(self.bob.pending_card_choice["choice_type"], "YES_NO")
        self.answer(self.bob, answer=True)
        self.assertEqual(self.bob.pending_card_choice["choice_type"], "SELECT_CARDS")
        self.assertTrue(self.answer(self.bob, selected_cards=["island_001"]))
        self.assertIn({"id": "island_001", "tapped": True}, self.bob.battlefield)

    def test_ponder_orders_privately_then_optionally_shuffles_and_draws(self):
        self.alice.library = ["island_001", "shock_001", "forest_001", "mountain_001"]
        self.resolve_item("ponder_001")
        self.assertEqual(self.alice.pending_card_choice["choice_type"], "ORDER_CARDS")
        self.assertFalse(any(b"island_001" in call.args[0] for call in self.bob.sock.sendall.call_args_list))
        token = self.alice.active_card_choice_seq_num
        self.assertFalse(self.game.pdu_dispatcher.handle(self.alice, {
            "type": "CARD_CHOICE_RESPONSE", "seq_num": token, "player_id": "alice",
            "ordered_cards": ["shock_001", "shock_001", "forest_001"],
        }))
        self.answer(self.alice, ordered_cards=["forest_001", "island_001", "shock_001"])
        self.assertEqual(self.alice.pending_card_choice["choice_type"], "YES_NO")
        self.answer(self.alice, answer=False)
        self.assertEqual(self.alice.hand, ["forest_001"])
        self.assertEqual(self.alice.library[:2], ["island_001", "shock_001"])

    def test_ponder_short_and_empty_libraries(self):
        for cards in (["island_001", "forest_001"], ["island_001"]):
            with self.subTest(count=len(cards)):
                self.alice.hand = []
                self.alice.graveyard = []
                self.alice.library = list(cards)
                self.resolve_item("ponder_001")
                self.assertEqual(self.alice.pending_card_choice["options"], cards)
                self.answer(self.alice, ordered_cards=list(reversed(cards)))
                self.answer(self.alice, answer=False)
                self.assertEqual(self.alice.hand, [cards[-1]])
        self.alice.hand = []
        self.alice.library = []
        self.resolve_item("ponder_002")
        self.assertIsNone(self.alice.pending_card_choice)
        self.assertEqual(self.alice.hand, [])

    def test_mana_leak_target_controller_decides_and_exact_payment_is_authoritative(self):
        target = {
            "stack_item_id": 40, "item_type": "SPELL", "source": "shock_001",
            "controller": "bob", "targets": ["alice"],
        }
        self.game.stack.append(target)
        self.bob.battlefield = [
            {"id": "island_001", "tapped": False},
            {"id": "island_002", "tapped": False},
            {"id": "island_003", "tapped": False},
        ]
        self.resolve_item("mana_leak_001", targets=[40])
        self.assertEqual(self.bob.pending_card_choice["choice_type"], "PAY_MANA")
        self.assertFalse(self.answer(self.bob, pay=True, mana_payment={"Generic": 2}))
        self.assertTrue(self.answer(self.bob, pay=True, mana_payment={"Generic": 3}))
        self.assertIn(target, self.game.stack)
        self.assertTrue(all(land["tapped"] for land in self.bob.battlefield))

        self.game.priority_holder = "alice"
        self.game.stack = [target]
        self.resolve_item("mana_leak_002", targets=[40])
        self.assertTrue(self.answer(self.bob, pay=False))
        self.assertNotIn(target, self.game.stack)
        self.assertIn("shock_001", self.bob.graveyard)

    def test_healing_salve_modes_and_prevention_consumption_cleanup(self):
        self.resolve_mode_item("healing_salve_001", "GAIN_LIFE", ["bob"])
        self.assertEqual(self.bob.life_total, 23)

        creature = {"id": "grizzly_bears_001", "power": 2, "toughness": 2, "damage": 0, "keywords": []}
        self.bob.battlefield = [creature]
        self.resolve_mode_item("healing_salve_002", "PREVENT_DAMAGE", [creature["id"]])
        self.assertEqual(creature["damage_prevention_shield"], 3)
        self.resolve_item("flame_slash_001", targets=[creature["id"]])
        self.assertEqual(creature["damage"], 1)
        self.assertEqual(creature["damage_prevention_shield"], 0)
        self.game.finish_cleanup()
        self.assertNotIn("damage_prevention_shield", creature)

    def test_healing_salve_cast_requires_known_mode_and_mode_legal_target(self):
        self.alice.hand = ["healing_salve_003"]
        self.alice.battlefield = [{"id": "plains_001", "tapped": False}]
        base = {
            "type": "CAST_SPELL", "seq_num": 10, "card_id": "healing_salve_003",
            "targets": ["alice"], "mana_payment": {"W": 1},
        }
        self.assertFalse(self.game.pdu_dispatcher.handle_cast_spell(self.alice, dict(base)))
        self.game.priority_holder = "alice"
        bad = dict(base, mode="UNKNOWN")
        self.assertFalse(self.game.pdu_dispatcher.handle_cast_spell(self.alice, bad))
        self.game.priority_holder = "alice"
        good = dict(base, mode="GAIN_LIFE")
        self.assertTrue(self.game.pdu_dispatcher.handle_cast_spell(self.alice, good))
        self.assertEqual(self.game.stack[-1]["mode"], "GAIN_LIFE")

    def test_rift_bolt_suspend_from_hand_through_upkeep_cast_and_resolution(self):
        self.alice.hand = ["rift_bolt_001"]
        self.alice.battlefield = [{"id": "mountain_001", "tapped": False}]
        self.assertTrue(self.game.pdu_dispatcher.handle(self.alice, {
            "type": "SUSPEND_CARD", "seq_num": 10, "player_id": "alice",
            "card_id": "rift_bolt_001", "mana_payment": {"R": 1},
        }))
        self.assertNotIn("rift_bolt_001", self.alice.hand)
        self.assertIn("rift_bolt_001", self.alice.exile)
        self.assertEqual(self.game.suspended_cards[0]["time_counters"], 1)

        self.game.upkeep()
        self.assertEqual(self.alice.pending_card_choice["choice_type"], "SELECT_TARGETS")
        self.assertIsNone(self.game.priority_holder)
        self.answer(self.alice, selected_targets=["bob"])
        self.assertNotIn("rift_bolt_001", self.alice.exile)
        self.assertEqual(self.game.stack[-1]["source"], "rift_bolt_001")
        self.assertTrue(self.game.stack[-1]["suspended"])
        self.game.resolve_top_stack_item()
        self.assertEqual(self.bob.life_total, 17)
        self.assertIn("rift_bolt_001", self.alice.graveyard)

    def test_suspend_rejects_wrong_card_cost_and_timing(self):
        self.alice.hand = ["rift_bolt_002", "shock_001"]
        self.alice.battlefield = [{"id": "mountain_001", "tapped": False}]
        common = {"type": "SUSPEND_CARD", "seq_num": 10, "player_id": "alice"}
        self.assertFalse(self.game.pdu_dispatcher.handle(self.alice, {
            **common, "card_id": "shock_001", "mana_payment": {"R": 1},
        }))
        self.game.priority_holder = "alice"
        self.assertFalse(self.game.pdu_dispatcher.handle(self.alice, {
            **common, "card_id": "rift_bolt_002", "mana_payment": {"R": 2},
        }))
        self.game.priority_holder = "alice"
        self.game.phase = "BEGIN_COMBAT"
        self.assertFalse(self.game.pdu_dispatcher.handle(self.alice, {
            **common, "card_id": "rift_bolt_002", "mana_payment": {"R": 1},
        }))


if __name__ == "__main__":
    unittest.main()
