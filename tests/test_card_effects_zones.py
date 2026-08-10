import unittest
from unittest.mock import MagicMock

from app.server.connected_client import ConnectedClient
from app.server.game import Game


class TestZoneAndAuraProductionPath(unittest.TestCase):
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
        result.exile = []
        result.battlefield = []
        result.life_total = 20
        result.mana_pool = {}
        return result

    def cast_and_resolve(self, card_id, target, payment):
        self.alice.hand.append(card_id)
        self.game.priority_holder = "alice"
        self.game.pdu_dispatcher.send_priority_grant(self.alice, "alice")
        self.assertTrue(self.game.pdu_dispatcher.handle_cast_spell(self.alice, {
            "type": "CAST_SPELL", "seq_num": self.alice.active_priority_seq_num,
            "card_id": card_id, "targets": [target], "mana_payment": payment,
        }))
        self.game.pdu_dispatcher.handle_priority_pass(self.alice, {
            "type": "PRIORITY_PASS", "seq_num": self.alice.active_priority_seq_num,
        })
        self.assertTrue(self.game.pdu_dispatcher.handle_priority_pass(self.bob, {
            "type": "PRIORITY_PASS", "seq_num": self.bob.active_priority_seq_num,
        }))

    def test_swords_exiles_and_gains_effective_power(self):
        target = {
            "id": "grizzly_bears_001", "tapped": False,
            "power": 2, "toughness": 2, "temp_power_buff": 3, "damage": 0,
        }
        self.bob.battlefield = [target]
        self.alice.battlefield = [{"id": "plains_001", "tapped": False}]
        self.cast_and_resolve(
            "swords_to_plowshares_001", target["id"], {"W": 1}
        )
        self.assertNotIn(target, self.bob.battlefield)
        self.assertIn(target["id"], self.bob.exile)
        self.assertEqual(self.bob.life_total, 25)
        state = self.game.state_builder.build_game_state(self.alice)
        self.assertEqual(state["exile"]["bob"], [target["id"]])

    def test_skullcrack_blocks_swords_life_gain(self):
        target = {
            "id": "grizzly_bears_001", "tapped": False,
            "power": 2, "toughness": 2, "damage": 0,
        }
        self.bob.battlefield = [target]
        self.alice.battlefield = [
            {"id": "mountain_001", "tapped": False},
            {"id": "mountain_002", "tapped": False},
            {"id": "plains_001", "tapped": False},
        ]
        self.cast_and_resolve("skullcrack_001", "bob", {"R": 1, "X": 1})
        self.cast_and_resolve(
            "swords_to_plowshares_001", target["id"], {"W": 1}
        )
        self.assertEqual(self.bob.life_total, 17)

    def test_pacifism_attaches_and_prevents_attacking(self):
        creature = {
            "id": "grizzly_bears_001", "tapped": False,
            "summoning_sick": False, "power": 2, "toughness": 2, "damage": 0,
        }
        self.alice.battlefield = [
            creature,
            {"id": "plains_001", "tapped": False},
            {"id": "plains_002", "tapped": False},
        ]
        self.cast_and_resolve("pacifism_001", creature["id"], {"W": 1, "X": 1})
        aura = next(
            permanent for permanent in self.alice.battlefield
            if permanent.get("id") == "pacifism_001"
        )
        self.assertEqual(aura["attached_to"], creature["id"])

        self.game.phase = "DECLARE_ATTACKERS"
        self.game.pdu_dispatcher.send_phase_transition(
            self.alice, "BEGIN_COMBAT", "DECLARE_ATTACKERS", "alice", 1
        )
        self.assertFalse(self.game.pdu_dispatcher.handle_declare_attackers(self.alice, {
            "type": "DECLARE_ATTACKERS",
            "seq_num": self.alice.active_phase_seq_num,
            "attackers": [{"creature_id": creature["id"], "target": "bob"}],
        }))

        self.game.destroy_permanent(creature["id"])
        self.game.post_event()
        self.assertIn("pacifism_001", self.alice.graveyard)

    def test_pacifism_prevents_blocking(self):
        attacker = {
            "id": "savannah_lions_001", "tapped": True,
            "power": 2, "toughness": 1, "damage": 0,
        }
        blocker = {
            "id": "grizzly_bears_001", "tapped": False,
            "power": 2, "toughness": 2, "damage": 0,
        }
        self.alice.battlefield = [
            attacker,
            {"id": "plains_001", "tapped": False},
            {"id": "plains_002", "tapped": False},
        ]
        self.bob.battlefield = [blocker]
        self.cast_and_resolve("pacifism_001", blocker["id"], {"W": 1, "X": 1})
        self.game.phase = "DECLARE_BLOCKERS"
        self.game.attackers = [{"creature_id": attacker["id"], "target": "bob"}]
        self.game.pdu_dispatcher.send_phase_transition(
            self.bob, "DECLARE_ATTACKERS", "DECLARE_BLOCKERS", "alice", 1
        )
        self.assertFalse(self.game.pdu_dispatcher.handle_declare_blockers(self.bob, {
            "type": "DECLARE_BLOCKERS",
            "seq_num": self.bob.active_phase_seq_num,
            "blockers": [{"creature_id": blocker["id"], "blocking_id": attacker["id"]}],
        }))


if __name__ == "__main__":
    unittest.main()
