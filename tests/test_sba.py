import unittest
from unittest.mock import MagicMock

from app.server.engine.effects import CardEffects
from app.server.engine.sba import StateBasedActions


class TestSBAAndEffects(unittest.TestCase):
    def setUp(self):
        self.game = MagicMock()
        self.alice = MagicMock()
        self.alice.pid = "alice"
        self.alice.life_total = 20
        self.alice.battlefield = []
        self.alice.graveyard = []
        self.alice.hand = []
        self.alice.library = ["forest_001"]
        self.alice.mana_pool = {}

        self.bob = MagicMock()
        self.bob.pid = "bob"
        self.bob.life_total = 20
        self.bob.battlefield = []
        self.bob.graveyard = []
        self.bob.hand = []
        self.bob.library = ["mountain_001"]
        self.bob.mana_pool = {}

        self.game.clients = [self.alice, self.bob]
        self.game.active_player = "alice"
        self.game.decked_players = set()


    def test_sba_lethal_damage(self):
        creature = {"id": "grizzly_bears_001", "toughness": 2, "damage": 2}
        self.alice.battlefield = [creature]

        changes, game_over = StateBasedActions.check_and_apply(self.game)
        self.assertNotIn(creature, self.alice.battlefield)
        self.assertIn("grizzly_bears_001", self.alice.graveyard)
        self.assertIsNone(game_over)

    def test_sba_simultaneous_zero_life_active_player_loses(self):
        self.alice.life_total = 0
        self.bob.life_total = 0

        changes, game_over = StateBasedActions.check_and_apply(self.game)
        self.assertIsNotNone(game_over)
        self.assertEqual(game_over["winner_id"], "bob")
        self.assertEqual(game_over["loser_id"], "alice")

    def test_effect_giant_growth(self):
        perm = {"id": "grizzly_bears_001", "power": 2, "toughness": 2}
        self.game.find_permanent.return_value = (self.alice, perm)

        status, changes = CardEffects.resolve_card_effect("giant_growth", "giant_growth_001", ["grizzly_bears_001"], self.alice, self.bob, self.game)
        self.assertEqual(status, "RESOLVED")
        self.assertEqual(perm["temp_power_buff"], 3)
        self.assertEqual(perm["temp_toughness_buff"], 3)

    def test_effect_dark_ritual(self):
        status, changes = CardEffects.resolve_card_effect("dark_ritual", "dark_ritual_001", [], self.alice, self.bob, self.game)
        self.assertEqual(status, "RESOLVED")
        self.assertEqual(self.alice.mana_pool["B"], 3)


if __name__ == "__main__":
    unittest.main()
