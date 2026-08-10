import unittest
from unittest.mock import MagicMock

from app.server.engine.triggers import EventBus, GameEvent, TriggerManager, calculate_devotion
from app.shared.card_catalog import CardCatalog


class TestTriggersEngine(unittest.TestCase):
    def setUp(self):
        self.mock_game = MagicMock()
        self.catalog = MagicMock()
        self.trigger_mgr = TriggerManager(self.mock_game, self.catalog)

    def test_goblin_guide_attack_trigger(self):
        event = GameEvent("attacker_declared", {"creature_id": "goblin_guide_001", "controller": "alice"})
        triggers = self.trigger_mgr.detect_triggers_for_event(event)
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].source_id, "goblin_guide_001")

        # Test resolution
        def_client = MagicMock()
        def_client.library = ["forest_001"]
        def_client.hand = []
        self.mock_game.other_player.return_value = "bob"
        self.mock_game.client_for_player.return_value = def_client
        self.catalog.get_card_data.return_value = {"card_type": "Land"}

        triggers[0].effect_fn({}, self.mock_game)
        self.assertEqual(len(def_client.hand), 1)
        self.assertEqual(def_client.hand[0], "forest_001")

    def test_phantasmal_bear_became_target_trigger(self):
        event = GameEvent("became_target", {"target_id": "phantasmal_bear_001", "controller": "alice"})
        triggers = self.trigger_mgr.detect_triggers_for_event(event)
        self.assertEqual(len(triggers), 1)
        self.assertEqual(triggers[0].source_id, "phantasmal_bear_001")

        owner = MagicMock()
        perm = {"id": "phantasmal_bear_001"}
        owner.battlefield = [perm]
        owner.graveyard = []
        self.mock_game.find_permanent.return_value = (owner, perm)

        triggers[0].effect_fn({}, self.mock_game)
        self.assertNotIn(perm, owner.battlefield)
        self.assertIn("phantasmal_bear_001", owner.graveyard)

    def test_devotion_calculation(self):
        battlefield = [
            {"id": "gray_merchant_001"},
            {"id": "black_knight_001"},
        ]
        self.catalog.get_card_data.side_effect = lambda cid: {
            "gray_merchant": {"mana_cost": {"B": 2}},
            "black_knight": {"mana_cost": {"B": 2}},
        }.get(cid, {})

        devotion = calculate_devotion(battlefield, "B", self.catalog)
        self.assertEqual(devotion, 4)


if __name__ == "__main__":
    unittest.main()
