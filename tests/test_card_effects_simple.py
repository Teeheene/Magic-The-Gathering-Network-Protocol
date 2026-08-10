import unittest
from unittest.mock import MagicMock

from app.server.connected_client import ConnectedClient
from app.server.game import Game


class TestSimpleCardEffectsProductionPath(unittest.TestCase):
    def setUp(self):
        self.connection = MagicMock()
        self.connection.clients = []
        self.connection.max_clients = 2
        self.connection.seq_num = 0
        self.game = Game(self.connection)
        self.alice = self.make_client("alice", 1001)
        self.bob = self.make_client("bob", 1002)
        self.connection.clients = self.game.clients = [self.alice, self.bob]
        self.game.phase = "PRECOMBAT_MAIN"
        self.game.active_player = "alice"

    @staticmethod
    def make_client(pid, port):
        client = ConnectedClient(MagicMock(), ("127.0.0.1", port))
        client.pid = pid
        client.hand = []
        client.library = []
        client.graveyard = []
        client.battlefield = []
        client.life_total = 20
        client.mana_pool = {}
        return client

    @staticmethod
    def land(card_id):
        return {"id": card_id, "tapped": False}

    def begin_priority(self):
        self.game.priority_holder = "alice"
        self.game.pdu_dispatcher.send_priority_grant(self.alice, "alice")

    def cast(self, card_id, targets, payment):
        self.alice.hand.append(card_id)
        self.begin_priority()
        result = self.game.pdu_dispatcher.handle_cast_spell(self.alice, {
            "type": "CAST_SPELL",
            "seq_num": self.alice.active_priority_seq_num,
            "card_id": card_id,
            "targets": list(targets),
            "mana_payment": dict(payment),
        })
        return result

    def resolve_top(self):
        self.assertTrue(self.game.pdu_dispatcher.handle_priority_pass(self.alice, {
            "type": "PRIORITY_PASS", "seq_num": self.alice.active_priority_seq_num,
        }))
        self.assertTrue(self.game.pdu_dispatcher.handle_priority_pass(self.bob, {
            "type": "PRIORITY_PASS", "seq_num": self.bob.active_priority_seq_num,
        }))
        self.assertEqual(self.game.priority_holder, "alice")

    def test_burn_family_normal_cast_resolution(self):
        cases = (
            ("lightning_bolt_001", {"R": 1}, "bob", 3),
            ("shock_001", {"R": 1}, "bob", 2),
            ("lava_spike_001", {"R": 1}, "bob", 3),
            ("flame_slash_001", {"R": 1}, "creature", 4),
            ("searing_spear_001", {"R": 1, "X": 1}, "bob", 3),
            ("skullcrack_001", {"R": 1, "X": 1}, "bob", 3),
            ("rift_bolt_001", {"R": 1, "X": 2}, "bob", 3),
            ("incinerate_001", {"R": 1, "X": 1}, "creature", 3),
        )
        for card_id, payment, target_kind, damage in cases:
            with self.subTest(card_id=card_id):
                self.setUp()
                self.alice.battlefield = [
                    self.land(f"mountain_{index:03d}")
                    for index in range(1, sum(payment.values()) + 1)
                ]
                target = "bob"
                if target_kind == "creature":
                    target = "leatherback_baloth_001"
                    self.bob.battlefield = [{
                        "id": target, "tapped": False, "power": 4,
                        "toughness": 5, "damage": 0,
                    }]
                self.assertTrue(self.cast(card_id, [target], payment))
                self.resolve_top()
                self.assertIn(card_id, self.alice.graveyard)
                if target == "bob":
                    self.assertEqual(self.bob.life_total, 20 - damage)
                else:
                    self.assertEqual(self.bob.battlefield[0]["damage"], damage)
                if card_id.startswith("skullcrack"):
                    self.assertTrue(self.game.cant_gain_life_this_turn)
                if card_id.startswith("incinerate"):
                    self.assertTrue(self.bob.battlefield[0]["cant_regenerate"])

    def test_giant_growth_cast_resolution_and_cleanup(self):
        target = {
            "id": "grizzly_bears_001", "tapped": False,
            "power": 2, "toughness": 2, "damage": 0,
        }
        self.alice.battlefield = [self.land("forest_001"), target]
        self.assertTrue(self.cast("giant_growth_001", [target["id"]], {"G": 1}))
        self.resolve_top()
        self.assertEqual(self.game.get_effective_pt(target), (5, 5))
        target["temp_power_buff"] = 0
        target["temp_toughness_buff"] = 0
        self.assertEqual(self.game.get_effective_pt(target), (2, 2))

    def test_raise_dead_cast_resolution(self):
        self.alice.graveyard = ["grizzly_bears_001"]
        self.alice.battlefield = [self.land("swamp_001")]
        self.assertTrue(self.cast(
            "raise_dead_001", ["grizzly_bears_001"], {"B": 1}
        ))
        self.resolve_top()
        self.assertIn("grizzly_bears_001", self.alice.hand)
        self.assertNotIn("grizzly_bears_001", self.alice.graveyard)
        self.assertIn("raise_dead_001", self.alice.graveyard)

    def test_dark_ritual_mana_is_spendable_by_normal_cast_path(self):
        self.alice.battlefield = [self.land("swamp_001")]
        self.assertTrue(self.cast("dark_ritual_001", [], {"B": 1}))
        self.resolve_top()
        self.assertEqual(self.alice.mana_pool, {"B": 3})

        self.alice.hand.append("mind_rot_001")
        self.begin_priority()
        self.assertTrue(self.game.pdu_dispatcher.handle_cast_spell(self.alice, {
            "type": "CAST_SPELL",
            "seq_num": self.alice.active_priority_seq_num,
            "card_id": "mind_rot_001",
            "targets": ["bob"],
            "mana_payment": {"B": 1, "X": 2},
        }))
        self.assertEqual(self.alice.mana_pool, {})

    def test_raise_dead_rejects_noncreature_graveyard_target(self):
        self.alice.graveyard = ["mountain_001"]
        self.alice.battlefield = [self.land("swamp_001")]
        self.assertFalse(self.cast("raise_dead_001", ["mountain_001"], {"B": 1}))
        self.assertIn("raise_dead_001", self.alice.hand)

    def test_cancel_and_negate_counter_through_cast_stack_path(self):
        for counter_id, payment, lands in (
            ("cancel_001", {"U": 2, "X": 1}, ["island_001", "island_002", "island_003"]),
            ("negate_001", {"U": 1, "X": 1}, ["island_001", "island_002"]),
        ):
            with self.subTest(counter_id=counter_id):
                self.setUp()
                self.game.active_player = "bob"
                self.bob.hand = ["lightning_bolt_001"]
                self.bob.battlefield = [self.land("mountain_001")]
                self.alice.hand = [counter_id]
                self.alice.battlefield = [self.land(card_id) for card_id in lands]
                self.game.priority_holder = "bob"
                self.game.pdu_dispatcher.send_priority_grant(self.bob, "bob")
                self.assertTrue(self.game.pdu_dispatcher.handle_cast_spell(self.bob, {
                    "type": "CAST_SPELL", "seq_num": self.bob.active_priority_seq_num,
                    "card_id": "lightning_bolt_001", "targets": ["alice"],
                    "mana_payment": {"R": 1},
                }))
                bolt_stack_id = self.game.stack[-1]["stack_item_id"]
                self.game.pdu_dispatcher.handle_priority_pass(self.bob, {
                    "type": "PRIORITY_PASS", "seq_num": self.bob.active_priority_seq_num,
                })
                self.assertTrue(self.game.pdu_dispatcher.handle_cast_spell(self.alice, {
                    "type": "CAST_SPELL", "seq_num": self.alice.active_priority_seq_num,
                    "card_id": counter_id, "targets": [bolt_stack_id],
                    "mana_payment": payment,
                }))
                self.game.pdu_dispatcher.handle_priority_pass(self.alice, {
                    "type": "PRIORITY_PASS", "seq_num": self.alice.active_priority_seq_num,
                })
                self.game.pdu_dispatcher.handle_priority_pass(self.bob, {
                    "type": "PRIORITY_PASS", "seq_num": self.bob.active_priority_seq_num,
                })
                self.assertFalse(any(
                    item.get("stack_item_id") == bolt_stack_id for item in self.game.stack
                ))
                self.assertIn("lightning_bolt_001", self.bob.graveyard)
                self.assertIn(counter_id, self.alice.graveyard)
                self.assertEqual(self.game.priority_holder, "bob")

    def test_terror_and_doom_blade_cast_restrictions_and_resolution(self):
        for spell_id in ("terror_001", "doom_blade_001"):
            with self.subTest(spell_id=spell_id):
                self.setUp()
                target = {
                    "id": "grizzly_bears_001", "tapped": False,
                    "power": 2, "toughness": 2, "damage": 0,
                }
                self.bob.battlefield = [target]
                self.alice.battlefield = [self.land("swamp_001"), self.land("swamp_002")]
                self.assertTrue(self.cast(spell_id, [target["id"]], {"B": 1, "X": 1}))
                self.resolve_top()
                self.assertIn(target["id"], self.bob.graveyard)

                self.setUp()
                black_target = {
                    "id": "black_knight_001", "tapped": False,
                    "power": 2, "toughness": 2, "damage": 0,
                }
                self.bob.battlefield = [black_target]
                self.alice.battlefield = [self.land("swamp_001"), self.land("swamp_002")]
                self.assertFalse(self.cast(spell_id, [black_target["id"]], {"B": 1, "X": 1}))

    def test_repeatable_artifact_and_assassin_abilities_use_full_activation_path(self):
        cases = (
            ("rod_of_ruin_001", {"tap": True, "mana": {"X": 3}}, ["bob"], 3),
            ("millstone_001", {"tap": True, "mana": {"X": 2}}, ["bob"], 2),
            ("royal_assassin_001", {"tap": True, "mana": {}}, ["grizzly_bears_001"], 0),
        )
        for source_id, cost, targets, land_count in cases:
            with self.subTest(source_id=source_id):
                self.setUp()
                source = {
                    "id": source_id, "tapped": False,
                    "summoning_sick": False,
                }
                self.alice.battlefield = [source] + [
                    self.land(f"swamp_{index:03d}") for index in range(1, land_count + 1)
                ]
                self.bob.library = ["forest_001", "forest_002", "forest_003"]
                self.bob.battlefield = [{
                    "id": "grizzly_bears_001", "tapped": True,
                    "power": 2, "toughness": 2, "damage": 0,
                }]
                self.begin_priority()
                self.assertTrue(self.game.pdu_dispatcher.handle_activate_ability(self.alice, {
                    "type": "ACTIVATE_ABILITY",
                    "seq_num": self.alice.active_priority_seq_num,
                    "source_id": source_id, "ability_index": 0,
                    "targets": targets, "cost_payment": cost,
                }))
                self.resolve_top()
                self.assertTrue(source["tapped"])
                if source_id.startswith("rod_of_ruin"):
                    self.assertEqual(self.bob.life_total, 19)
                elif source_id.startswith("millstone"):
                    self.assertEqual(self.bob.library, ["forest_003"])
                    self.assertEqual(self.bob.graveyard, ["forest_001", "forest_002"])
                else:
                    self.assertIn("grizzly_bears_001", self.bob.graveyard)


if __name__ == "__main__":
    unittest.main()
