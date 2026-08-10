import unittest
from unittest.mock import MagicMock
from app.server.game import Game
from app.server.connected_client import ConnectedClient


class TestBaseFiveE2E(unittest.TestCase):
    def setUp(self):
        self.mock_connection = MagicMock()
        self.mock_connection.clients = []
        self.game = Game(self.mock_connection)
        self.game.phase = "PRECOMBAT_MAIN"
        self.game.active_player = "alice"
        self.game.priority_holder = "alice"

    def create_mock_client(self, pid, socket_fileno):
        mock_socket = MagicMock()
        mock_socket.fileno.return_value = socket_fileno
        c = ConnectedClient(sock=mock_socket, address=("127.0.0.1", socket_fileno))
        c.pid = pid
        c.hand = []
        c.battlefield = []
        c.graveyard = []
        c.library = []
        c.life_total = 20
        c.mana_pool = {}
        return c

    def test_lightning_bolt_e2e(self):
        """Lightning Bolt targets player, deals 3 damage, goes to graveyard, SBA checked."""
        c1 = self.create_mock_client("alice", 1001)
        c1.hand = ["lightning_bolt_001"]
        c1.battlefield = [{"id": "mountain_001", "tapped": False}]
        c2 = self.create_mock_client("bob", 1002)

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")

        pdu = {
            "type": "CAST_SPELL",
            "seq_num": c1.active_priority_seq_num,
            "card_id": "lightning_bolt_001",
            "targets": ["bob"],
            "mana_payment": {"R": 1}
        }
        res = self.game.pdu_dispatcher.handle_cast_spell(c1, pdu)
        self.assertTrue(res)
        self.assertEqual(len(self.game.stack), 1)

        # Pass priority twice to resolve
        self.game.pdu_dispatcher.handle_priority_pass(c1, {"type": "PRIORITY_PASS", "seq_num": c1.active_priority_seq_num})
        self.game.pdu_dispatcher.handle_priority_pass(c2, {"type": "PRIORITY_PASS", "seq_num": c2.active_priority_seq_num})

        self.assertEqual(c2.life_total, 17)
        self.assertIn("lightning_bolt_001", c1.graveyard)

    def test_flame_slash_e2e(self):
        """Flame Slash: creature-only target, 4 damage, lethal death."""
        c1 = self.create_mock_client("alice", 1001)
        c1.hand = ["flame_slash_001"]
        c1.battlefield = [{"id": "mountain_001", "tapped": False}]
        c2 = self.create_mock_client("bob", 1002)
        c2.battlefield = [{"id": "grizzly_bears_001", "tapped": False, "power": 2, "toughness": 2, "damage": 0}]

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")

        # Player target must be rejected
        bad_pdu = {
            "type": "CAST_SPELL",
            "seq_num": c1.active_priority_seq_num,
            "card_id": "flame_slash_001",
            "targets": ["bob"],
            "mana_payment": {"R": 1}
        }
        self.assertFalse(self.game.pdu_dispatcher.handle_cast_spell(c1, bad_pdu))

        # Creature target succeeds
        pdu = {
            "type": "CAST_SPELL",
            "seq_num": c1.active_priority_seq_num,
            "card_id": "flame_slash_001",
            "targets": ["grizzly_bears_001"],
            "mana_payment": {"R": 1}
        }
        self.assertTrue(self.game.pdu_dispatcher.handle_cast_spell(c1, pdu))

        # Pass priority twice to resolve
        self.game.pdu_dispatcher.handle_priority_pass(c1, {"type": "PRIORITY_PASS", "seq_num": c1.active_priority_seq_num})
        self.game.pdu_dispatcher.handle_priority_pass(c2, {"type": "PRIORITY_PASS", "seq_num": c2.active_priority_seq_num})

        self.assertEqual(len(c2.battlefield), 0)
        self.assertIn("grizzly_bears_001", c2.graveyard)
        self.assertIn("flame_slash_001", c1.graveyard)

    def test_counterspell_zone_movement_e2e(self):
        """Req 2: Lightning Bolt cast by Bob, Counterspell cast by Alice -> Bolt card enters Bob graveyard, Counterspell enters Alice graveyard, Bob takes 0 damage."""
        c1 = self.create_mock_client("alice", 1001)
        c1.hand = ["counterspell_001"]
        c1.battlefield = [{"id": "island_001", "tapped": False}, {"id": "island_002", "tapped": False}]

        c2 = self.create_mock_client("bob", 1002)
        c2.hand = ["lightning_bolt_001"]
        c2.battlefield = [{"id": "mountain_001", "tapped": False}]

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.active_player = "bob"
        self.game.priority_holder = "bob"

        self.game.pdu_dispatcher.send_priority_grant(c2, "bob")

        # Bob casts Lightning Bolt targeting Alice
        bolt_pdu = {
            "type": "CAST_SPELL",
            "seq_num": c2.active_priority_seq_num,
            "card_id": "lightning_bolt_001",
            "targets": ["alice"],
            "mana_payment": {"R": 1}
        }
        self.assertTrue(self.game.pdu_dispatcher.handle_cast_spell(c2, bolt_pdu))
        bolt_stack_id = self.game.stack[0]["stack_item_id"]

        # Bob passes priority to Alice
        self.game.pdu_dispatcher.handle_priority_pass(c2, {"type": "PRIORITY_PASS", "seq_num": c2.active_priority_seq_num})
        self.assertEqual(self.game.priority_holder, "alice")

        # Alice casts Counterspell targeting Bolt
        cs_pdu = {
            "type": "CAST_SPELL",
            "seq_num": c1.active_priority_seq_num,
            "card_id": "counterspell_001",
            "targets": [bolt_stack_id],
            "mana_payment": {"U": 2}
        }
        self.assertTrue(self.game.pdu_dispatcher.handle_cast_spell(c1, cs_pdu))

        # Alice passes, Bob passes -> Counterspell resolves
        self.game.pdu_dispatcher.handle_priority_pass(c1, {"type": "PRIORITY_PASS", "seq_num": c1.active_priority_seq_num})
        self.game.pdu_dispatcher.handle_priority_pass(c2, {"type": "PRIORITY_PASS", "seq_num": c2.active_priority_seq_num})

        # Counterspell resolved and removed Bolt from stack. Bolt card went to Bob's graveyard. Counterspell went to Alice's graveyard.
        self.assertIn("lightning_bolt_001", c2.graveyard)
        self.assertIn("counterspell_001", c1.graveyard)
        self.assertEqual(len(self.game.stack), 0)
        self.assertEqual(c1.life_total, 20)

    def test_unsummon_e2e(self):
        """Unsummon returns target creature to owner's hand."""
        c1 = self.create_mock_client("alice", 1001)
        c1.hand = ["unsummon_001"]
        c1.battlefield = [{"id": "island_001", "tapped": False}]

        c2 = self.create_mock_client("bob", 1002)
        c2.battlefield = [{"id": "grizzly_bears_001", "tapped": False, "power": 2, "toughness": 2, "damage": 0}]

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")

        pdu = {
            "type": "CAST_SPELL",
            "seq_num": c1.active_priority_seq_num,
            "card_id": "unsummon_001",
            "targets": ["grizzly_bears_001"],
            "mana_payment": {"U": 1}
        }
        self.assertTrue(self.game.pdu_dispatcher.handle_cast_spell(c1, pdu))

        # Pass priority twice to resolve
        self.game.pdu_dispatcher.handle_priority_pass(c1, {"type": "PRIORITY_PASS", "seq_num": c1.active_priority_seq_num})
        self.game.pdu_dispatcher.handle_priority_pass(c2, {"type": "PRIORITY_PASS", "seq_num": c2.active_priority_seq_num})

        self.assertIn("grizzly_bears_001", c2.hand)
        self.assertEqual(len(c2.battlefield), 0)
        self.assertIn("unsummon_001", c1.graveyard)

    def test_naturalize_e2e(self):
        """Naturalize destroys artifact/enchantment and rejects creature target."""
        c1 = self.create_mock_client("alice", 1001)
        c1.hand = ["naturalize_001"]
        c1.battlefield = [{"id": "forest_001", "tapped": False}, {"id": "forest_002", "tapped": False}]

        c2 = self.create_mock_client("bob", 1002)
        c2.battlefield = [
            {"id": "rod_of_ruin_001", "tapped": False},
            {"id": "grizzly_bears_001", "tapped": False, "power": 2, "toughness": 2, "damage": 0}
        ]

        self.mock_connection.clients = [c1, c2]
        self.game.clients = [c1, c2]
        self.game.pdu_dispatcher.send_priority_grant(c1, "alice")

        # Creature target rejected
        bad_pdu = {
            "type": "CAST_SPELL",
            "seq_num": c1.active_priority_seq_num,
            "card_id": "naturalize_001",
            "targets": ["grizzly_bears_001"],
            "mana_payment": {"G": 1, "C": 1}
        }
        self.assertFalse(self.game.pdu_dispatcher.handle_cast_spell(c1, bad_pdu))

        # Artifact target succeeds
        pdu = {
            "type": "CAST_SPELL",
            "seq_num": c1.active_priority_seq_num,
            "card_id": "naturalize_001",
            "targets": ["rod_of_ruin_001"],
            "mana_payment": {"G": 1, "X": 1}
        }
        self.assertTrue(self.game.pdu_dispatcher.handle_cast_spell(c1, pdu))

        # Pass priority twice to resolve
        self.game.pdu_dispatcher.handle_priority_pass(c1, {"type": "PRIORITY_PASS", "seq_num": c1.active_priority_seq_num})
        self.game.pdu_dispatcher.handle_priority_pass(c2, {"type": "PRIORITY_PASS", "seq_num": c2.active_priority_seq_num})

        self.assertIn("rod_of_ruin_001", c2.graveyard)
        self.assertIn("naturalize_001", c1.graveyard)
