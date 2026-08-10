import unittest
from unittest.mock import MagicMock

from app.server.connected_client import ConnectedClient
from app.server.game import Game


class TestManaAndAbilityProductionPath(unittest.TestCase):
    def setUp(self):
        connection = MagicMock()
        connection.clients = []
        connection.max_clients = 2
        connection.seq_num = 0
        self.game = Game(connection)
        self.alice = self.client("alice", 1001)
        self.bob = self.client("bob", 1002)
        connection.clients = self.game.clients = [self.alice, self.bob]
        self.game.phase = "PRECOMBAT_MAIN"
        self.game.active_player = "alice"

    @staticmethod
    def client(pid, port):
        result = ConnectedClient(MagicMock(), ("127.0.0.1", port))
        result.pid = pid
        result.hand = []
        result.library = []
        result.graveyard = []
        result.battlefield = []
        result.life_total = 20
        result.mana_pool = {}
        return result

    def grant(self, client):
        self.game.priority_holder = client.pid
        self.game.pdu_dispatcher.send_priority_grant(client, client.pid)

    def cast(self, client, card_id, targets, payment):
        client.hand.append(card_id)
        self.grant(client)
        return self.game.pdu_dispatcher.handle_cast_spell(client, {
            "type": "CAST_SPELL", "seq_num": client.active_priority_seq_num,
            "card_id": card_id, "targets": targets, "mana_payment": payment,
        })

    def resolve(self, first, second):
        self.game.pdu_dispatcher.handle_priority_pass(first, {
            "type": "PRIORITY_PASS", "seq_num": first.active_priority_seq_num,
        })
        return self.game.pdu_dispatcher.handle_priority_pass(second, {
            "type": "PRIORITY_PASS", "seq_num": second.active_priority_seq_num,
        })

    def test_elves_are_implicit_green_sources_with_tap_and_sickness_rules(self):
        for source_id in ("llanowar_elves_001", "elvish_mystic_001"):
            with self.subTest(source_id=source_id):
                self.setUp()
                creature = {
                    "id": source_id, "tapped": False, "summoning_sick": False,
                    "power": 1, "toughness": 1, "damage": 0,
                }
                target = {
                    "id": "grizzly_bears_001", "tapped": False,
                    "power": 2, "toughness": 2, "damage": 0,
                }
                self.alice.battlefield = [creature, target]
                self.assertTrue(self.cast(
                    self.alice, "giant_growth_001", [target["id"]], {"G": 1}
                ))
                self.assertTrue(creature["tapped"])

                self.setUp()
                sick_creature = {
                    "id": source_id, "tapped": False, "summoning_sick": True,
                    "power": 1, "toughness": 1, "damage": 0,
                }
                self.alice.battlefield = [sick_creature, target.copy()]
                self.assertFalse(self.cast(
                    self.alice, "giant_growth_001", [target["id"]], {"G": 1}
                ))
                self.assertFalse(sick_creature["tapped"])

    def test_sol_ring_produces_two_colorless_for_generic_payment(self):
        ring = {"id": "sol_ring_001", "tapped": False}
        swamp = {"id": "swamp_001", "tapped": False}
        target = {
            "id": "grizzly_bears_001", "tapped": False,
            "power": 2, "toughness": 2, "damage": 0,
        }
        self.alice.battlefield = [ring, swamp]
        self.bob.battlefield = [target]
        self.assertTrue(self.cast(
            self.alice, "mind_rot_001", ["bob"], {"B": 1, "X": 2}
        ))
        self.assertTrue(ring["tapped"])
        self.assertTrue(swamp["tapped"])

    def test_troll_hexproof_rejects_opponent_target_but_allows_controller(self):
        troll = {
            "id": "troll_ascetic_001", "tapped": False,
            "summoning_sick": False, "power": 3, "toughness": 2, "damage": 0,
            "keywords": ["hexproof"],
        }
        self.alice.battlefield = [troll, {"id": "forest_001", "tapped": False}]
        self.bob.battlefield = [
            {"id": "swamp_001", "tapped": False},
            {"id": "swamp_002", "tapped": False},
        ]
        self.game.active_player = "bob"
        self.assertFalse(self.cast(
            self.bob, "doom_blade_001", [troll["id"]], {"B": 1, "X": 1}
        ))

        self.game.active_player = "alice"
        self.assertTrue(self.cast(
            self.alice, "giant_growth_001", [troll["id"]], {"G": 1}
        ))

    def test_troll_regeneration_shield_prevents_lethal_sba_once(self):
        troll = {
            "id": "troll_ascetic_001", "tapped": False,
            "summoning_sick": False, "power": 3, "toughness": 2,
            "damage": 0, "keywords": ["hexproof"],
        }
        self.alice.battlefield = [
            troll,
            {"id": "forest_001", "tapped": False},
            {"id": "forest_002", "tapped": False},
        ]
        self.grant(self.alice)
        self.assertTrue(self.game.pdu_dispatcher.handle_activate_ability(self.alice, {
            "type": "ACTIVATE_ABILITY",
            "seq_num": self.alice.active_priority_seq_num,
            "source_id": troll["id"], "ability_index": 0,
            "targets": [], "cost_payment": {"tap": False, "mana": {"G": 1, "X": 1}},
        }))
        self.resolve(self.alice, self.bob)
        self.assertTrue(troll["regeneration_shield"])

        troll["damage"] = 2
        self.game.post_event()
        self.assertIn(troll, self.alice.battlefield)
        self.assertEqual(troll["damage"], 0)
        self.assertTrue(troll["tapped"])
        self.assertFalse(troll["regeneration_shield"])

    def test_terror_and_incinerate_honor_no_regeneration(self):
        for spell_id, payment, lands in (
            ("terror_001", {"B": 1, "X": 1}, ["swamp_001", "swamp_002"]),
            ("incinerate_001", {"R": 1, "X": 1}, ["mountain_001", "mountain_002"]),
        ):
            with self.subTest(spell_id=spell_id):
                self.setUp()
                troll = {
                    "id": "troll_ascetic_001", "tapped": False,
                    "summoning_sick": False, "power": 3, "toughness": 2,
                    "damage": 0, "keywords": ["hexproof"],
                    "regeneration_shield": True,
                }
                self.alice.battlefield = [troll] + [
                    {"id": card_id, "tapped": False} for card_id in lands
                ]
                self.assertTrue(self.cast(
                    self.alice, spell_id, [troll["id"]], payment
                ))
                self.resolve(self.alice, self.bob)
                self.assertNotIn(troll, self.alice.battlefield)
                self.assertIn(troll["id"], self.alice.graveyard)


if __name__ == "__main__":
    unittest.main()
