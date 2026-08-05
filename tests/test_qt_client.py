import unittest
from PySide6.QtWidgets import QApplication
from app.client.state import ClientState
from app.client.actions import ClientActionFactory
from app.client.controller import ClientController
from app.client.qt.views.connection_view import ConnectionView
from app.client.qt.views.lobby_view import LobbyView
from app.client.qt.views.game_view import GameView
from app.client.qt.views.game_over_view import GameOverView
from app.client.qt.dialogs.mulligan_dialog import MulliganDialog
from app.client.qt.dialogs.discard_dialog import DiscardDialog
from app.client.qt.dialogs.damage_order_dialog import DamageOrderDialog

_app = QApplication.instance() or QApplication([])

class TestPySide6Client(unittest.TestCase):
    def setUp(self):
        self.controller = ClientController(verbose=False)

    def tearDown(self):
        self.controller.cleanup()

    def test_state_authoritative_update(self):
        st = ClientState()
        pdu = {
            "type": "GAME_STATE_UPDATE",
            "seq_num": 10,
            "state": {
                "turn": 2,
                "phase": "PRECOMBAT_MAIN",
                "life_totals": {"player_1": 20, "player_2": 20},
                "hand": ["mountain_001", "shock_001"],
                "hand_counts": {"player_2": 5}
            }
        }
        st.update_authoritative_state(pdu)
        self.assertEqual(st.current_state["phase"], "PRECOMBAT_MAIN")
        self.assertEqual(st.current_state["hand"], ["mountain_001", "shock_001"])
        self.assertNotIn("counterspell_001", str(st.current_state)) # Opponent hand hidden

    def test_action_factory_pdus(self):
        p_pass = ClientActionFactory.priority_pass(42)
        self.assertEqual(p_pass, {"type": "PRIORITY_PASS", "seq_num": 42})

        p_cast = ClientActionFactory.cast_spell(42, "shock_001", ["player_2"])
        self.assertEqual(p_cast["type"], "CAST_SPELL")
        self.assertEqual(p_cast["targets"], ["player_2"])

        p_land = ClientActionFactory.play_land(42, "mountain_001")
        self.assertEqual(p_land["type"], "PLAY_LAND")

        p_atk = ClientActionFactory.declare_attackers(42, [{"creature_id": "goblin_guide_001", "target": "player_2"}])
        self.assertEqual(p_atk["type"], "DECLARE_ATTACKERS")

        p_mull = ClientActionFactory.mulligan_choice(42, keep=True, cards_to_bottom=["card_1"])
        self.assertEqual(p_mull, {"type": "MULLIGAN_CHOICE", "seq_num": 42, "keep": True, "cards_to_bottom": ["card_1"]})

    def test_connection_and_lobby_views(self):
        cv = ConnectionView()
        self.assertEqual(cv.host_input.text(), "127.0.0.1")
        self.assertEqual(cv.port_input.text(), "4444")

        lv = LobbyView()
        lv.update_state("player_1", {"phase": "LOBBY", "players_ready": 1, "waiting_for": "player_2"})
        self.assertIn("Player ID: player_1", lv.player_id_lbl.text())

    def test_game_view_update(self):
        gv = GameView()
        sample_state = {
            "turn": 1,
            "phase": "PRECOMBAT_MAIN",
            "active_player": "player_1",
            "priority_holder": "player_1",
            "life_totals": {"player_1": 20, "player_2": 20},
            "library_counts": {"player_1": 40, "player_2": 40},
            "graveyard": {"player_1": [], "player_2": []},
            "hand_counts": {"player_2": 7},
            "hand": ["mountain_001", "lightning_bolt_001"],
            "battlefield": {"player_1": [], "player_2": []},
            "stack": []
        }
        gv.update_view(sample_state, "player_1")
        self.assertIn("Turn: 1", gv.phase_bar.info_lbl.text())
        self.assertIn("Life: 20", gv.local_hud.life_lbl.text())

    def test_game_over_view(self):
        gov = GameOverView()
        gov.set_result("player_1", "Opponent Conceded", "player_1")
        self.assertIn("VICTORY", gov.winner_lbl.text())

    def test_mulligan_dialog(self):
        hand = ["mountain_001", "shock_001", "bolt_001"]
        dlg = MulliganDialog(hand=hand, mulligans_taken=1)
        self.assertEqual(dlg.mulligans_taken, 1)

    def test_discard_dialog(self):
        hand = ["mountain_001", "shock_001", "bolt_001"]
        dlg = DiscardDialog(hand=hand, count=1)
        self.assertEqual(dlg.required_count, 1)

    def test_damage_order_dialog(self):
        dlg = DamageOrderDialog(attacker_id="goblin_guide_001", blockers=["bears_001", "elf_001"])
        self.assertEqual(dlg.attacker_id, "goblin_guide_001")
        self.assertEqual(len(dlg.blockers), 2)

if __name__ == "__main__":
    unittest.main()
