import unittest
from unittest.mock import MagicMock

from app.server.connected_client import ConnectedClient
from app.server.game import Game


class TestProtocolCompatibleRemainder(unittest.TestCase):
    def setUp(self):
        connection = MagicMock()
        connection.clients = []
        connection.max_clients = 2
        connection.seq_num = 0
        self.game = Game(connection)
        self.alice = self.client("alice", 1001)
        self.bob = self.client("bob", 1002)
        connection.clients[:] = [self.alice, self.bob]
        self.game.clients = connection.clients
        self.game.active_player = "alice"
        self.game.priority_holder = "alice"
        self.game.phase = "PRECOMBAT_MAIN"

    @staticmethod
    def client(pid, port):
        client = ConnectedClient(MagicMock(), ("127.0.0.1", port))
        client.pid = pid
        client.hand = []
        client.battlefield = []
        client.graveyard = []
        client.library = []
        client.life_total = 20
        client.active_priority_seq_num = 10
        client.active_phase_seq_num = 10
        client.mana_pool = {}
        return client

    @staticmethod
    def land(card_id):
        return {"id": card_id, "tapped": False}

    def cast(self, card_id, targets, payment):
        self.alice.hand = [card_id]
        return self.game.pdu_dispatcher.handle_cast_spell(self.alice, {
            "type": "CAST_SPELL", "seq_num": 10, "card_id": card_id,
            "targets": targets, "mana_payment": payment,
        })

    def test_bushwhacker_exact_normal_and_kicked_payments_and_cleanup(self):
        self.alice.battlefield = [self.land("mountain_001")]
        self.assertTrue(self.cast("goblin_bushwhacker_001", [], {"R": 1}))
        self.assertFalse(self.game.stack[-1]["kicked"])
        self.game.resolve_top_stack_item()
        self.assertFalse(self.game.stack)

        self.game.priority_holder = "alice"
        self.alice.battlefield = [
            self.land("mountain_001"), self.land("mountain_002"), self.land("forest_001"),
            {"id": "grizzly_bears_001", "power": 2, "toughness": 2, "summoning_sick": True, "keywords": []},
        ]
        self.assertTrue(self.cast("goblin_bushwhacker_002", [], {"R": 2, "Generic": 1}))
        self.assertTrue(self.game.stack[-1]["kicked"])
        self.game.resolve_top_stack_item()
        self.assertEqual(self.game.stack[-1]["item_type"], "TRIGGER_ABILITY")
        self.game.resolve_top_stack_item()
        creatures = [p for p in self.alice.battlefield if "creature" in (self.game.card_data(p["id"]) or {}).get("card_type", "").casefold()]
        self.assertTrue(all(p.get("temp_power_buff") == 1 for p in creatures))
        self.assertTrue(all("haste" in self.game.permanent_keywords(p) for p in creatures))
        self.game.phase = "DECLARE_ATTACKERS"
        self.game.priority_holder = "alice"
        self.assertTrue(self.game.pdu_dispatcher.handle_declare_attackers(self.alice, {
            "type": "DECLARE_ATTACKERS", "seq_num": 10,
            "attackers": [{"creature_id": "goblin_bushwhacker_002", "target": "bob"}],
        }))
        self.game.finish_cleanup()
        self.assertTrue(all(p.get("temp_power_buff") == 0 for p in creatures))
        self.assertTrue(all("haste" not in self.game.permanent_keywords(p) for p in creatures))

    def test_bushwhacker_rejects_intermediate_extra_and_insufficient_payment(self):
        for payment in ({"R": 2}, {"R": 2, "Generic": 2}):
            self.game.priority_holder = "alice"
            self.alice.battlefield = [self.land("mountain_001"), self.land("mountain_002"), self.land("forest_001")]
            self.assertFalse(self.cast("goblin_bushwhacker_003", [], payment))
        self.game.priority_holder = "alice"
        self.alice.battlefield = [self.land("mountain_001")]
        self.assertFalse(self.cast("goblin_bushwhacker_004", [], {"R": 2, "Generic": 1}))

    def test_vines_normal_kicked_invalid_insufficient_and_cleanup(self):
        target = {"id": "grizzly_bears_001", "power": 2, "toughness": 2, "keywords": []}
        self.bob.battlefield = [target]
        self.alice.battlefield = [self.land("forest_001")]
        self.assertTrue(self.cast("vines_of_vastwood_001", [target["id"]], {"G": 1}))
        self.game.resolve_top_stack_item()
        self.assertTrue(target["opponent_targeting_blocked_until_eot"])
        self.assertEqual(self.game.get_effective_pt(target), (2, 2))
        self.assertFalse(self.game.targets_are_legal("shock_001", [target["id"]], controller_id="alice"))
        self.assertTrue(self.game.targets_are_legal("giant_growth_001", [target["id"]], controller_id="bob"))
        self.game.finish_cleanup()

        self.game.active_player = "alice"
        self.game.phase = "PRECOMBAT_MAIN"
        self.game.priority_holder = "alice"
        self.alice.battlefield = [self.land("forest_001"), self.land("forest_002")]
        self.assertTrue(self.cast("vines_of_vastwood_002", [target["id"]], {"G": 2}))
        self.game.resolve_top_stack_item()
        self.assertEqual(self.game.get_effective_pt(target), (6, 6))
        self.game.finish_cleanup()
        self.assertEqual(self.game.get_effective_pt(target), (2, 2))
        self.assertNotIn("opponent_targeting_blocked_until_eot", target)

        for payment, lands in [({"G": 1, "Generic": 1}, 2), ({"G": 3}, 3), ({"G": 2}, 1)]:
            self.game.active_player = "alice"
            self.game.priority_holder = "alice"
            self.game.phase = "PRECOMBAT_MAIN"
            self.alice.battlefield = [self.land(f"forest_{i:03d}") for i in range(1, lands + 1)]
            self.assertFalse(self.cast("vines_of_vastwood_003", [target["id"]], payment))

    def test_flying_reach_and_protection_legality(self):
        flyer = {"id": "air_elemental_001", "keywords": ["flying"], "summoning_sick": False}
        ground = {"id": "grizzly_bears_001", "keywords": []}
        reach = {"id": "grizzly_bears_002", "keywords": ["reach"]}
        self.alice.battlefield = [flyer]
        self.bob.battlefield = [ground, reach]
        self.game.phase = "DECLARE_BLOCKERS"
        self.game.attackers = [{"creature_id": flyer["id"], "target": "bob"}]
        self.assertFalse(self.game.pdu_dispatcher.handle_declare_blockers(self.bob, {
            "type": "DECLARE_BLOCKERS", "seq_num": 10,
            "blockers": [{"creature_id": ground["id"], "blocking_id": flyer["id"]}],
        }))
        self.assertTrue(self.game.pdu_dispatcher.handle_declare_blockers(self.bob, {
            "type": "DECLARE_BLOCKERS", "seq_num": 10,
            "blockers": [{"creature_id": reach["id"], "blocking_id": flyer["id"]}],
        }))

        for flyer_id in ("air_elemental_001", "serra_angel_001", "ornithopter_001"):
            self.game.phase = "DECLARE_BLOCKERS"
            self.alice.battlefield = [{"id": flyer_id, "keywords": ["flying"]}]
            self.bob.battlefield = [ground]
            self.game.attackers = [{"creature_id": flyer_id, "target": "bob"}]
            self.assertFalse(self.game.pdu_dispatcher.handle_declare_blockers(self.bob, {
                "type": "DECLARE_BLOCKERS", "seq_num": 10,
                "blockers": [{"creature_id": ground["id"], "blocking_id": flyer_id}],
            }))

        white = {"id": "white_knight_001", "power": 2, "toughness": 2, "keywords": ["first_strike", "protection_from_black"], "damage": 0}
        black = {"id": "black_knight_001", "power": 2, "toughness": 2, "keywords": ["first_strike", "protection_from_white"], "damage": 0}
        self.alice.battlefield = [white]
        self.bob.battlefield = [black]
        self.assertFalse(self.game.targets_are_legal("doom_blade_001", [white["id"]], controller_id="bob"))
        self.assertFalse(self.game.targets_are_legal("swords_to_plowshares_001", [black["id"]], controller_id="alice"))
        self.game.phase = "DECLARE_BLOCKERS"
        self.game.attackers = [{"creature_id": white["id"], "target": "bob"}]
        self.assertFalse(self.game.pdu_dispatcher.handle_declare_blockers(self.bob, {
            "type": "DECLARE_BLOCKERS", "seq_num": 10,
            "blockers": [{"creature_id": black["id"], "blocking_id": white["id"]}],
        }))
        self.game.blockers = [{"creature_id": black["id"], "blocking_id": white["id"]}]
        self.game.damage_orders = {white["id"]: [black["id"]]}
        self.game.resolve_combat_damage(True)
        self.assertEqual(white["damage"], 0)
        self.assertEqual(black["damage"], 0)

    def test_reckless_wurm_normal_cast_enters_as_creature(self):
        self.alice.battlefield = [
            self.land("mountain_001"), self.land("mountain_002"),
            self.land("mountain_003"), self.land("mountain_004"),
        ]
        self.assertTrue(self.cast("reckless_wurm_001", [], {"R": 1, "Generic": 3}))
        self.assertFalse(self.game.stack[-1]["kicked"])
        self.game.resolve_top_stack_item()
        self.assertIn("reckless_wurm_001", [p["id"] for p in self.alice.battlefield])

    def test_first_and_double_strike_damage_windows(self):
        first = {"id": "white_knight_001", "power": 2, "toughness": 2, "keywords": ["first_strike"], "damage": 0}
        double = {"id": "grizzly_bears_001", "power": 2, "toughness": 4, "keywords": ["double_strike"], "damage": 0}
        self.alice.battlefield = [first, double]
        self.game.attackers = [
            {"creature_id": first["id"], "target": "bob"},
            {"creature_id": double["id"], "target": "bob"},
        ]
        self.game.resolve_combat_damage(True)
        self.assertEqual(self.bob.life_total, 16)
        self.game.resolve_combat_damage(False)
        self.assertEqual(self.bob.life_total, 14)

    def test_skullcrack_sets_both_turn_restrictions_and_cleanup(self):
        self.game.stack.append({
            "stack_item_id": 1, "item_type": "SPELL", "source": "skullcrack_001",
            "controller": "alice", "targets": ["bob"],
        })
        self.game.resolve_top_stack_item()
        self.assertTrue(self.game.cant_gain_life_this_turn)
        self.assertTrue(self.game.cant_prevent_damage_this_turn)
        self.assertEqual(self.game.gain_life(self.bob, 3), 0)
        self.game.finish_cleanup()
        self.assertFalse(self.game.cant_gain_life_this_turn)
        self.assertFalse(self.game.cant_prevent_damage_this_turn)


if __name__ == "__main__":
    unittest.main()
