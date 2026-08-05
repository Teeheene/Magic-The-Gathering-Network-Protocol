import unittest
import tkinter as tk
from unittest.mock import patch
from typing import Dict, Any, List
from app.client.gui import GraphicalGameClient
from app.client.state import ClientState

class TestGraphicalClientUI(unittest.TestCase):
    def setUp(self):
        self.sent_pdus: List[Dict[str, Any]] = []
        def send_fn(pdu: Dict[str, Any]):
            self.sent_pdus.append(pdu)

        self.client_state = ClientState()
        try:
            self.app = GraphicalGameClient(client_state=self.client_state, send_action_fn=send_fn)
            if hasattr(self.app, "_after_id") and self.app._after_id:
                try:
                    self.app.after_cancel(self.app._after_id)
                except Exception:
                    pass
            self.app._after_id = None
        except tk.TclError:
            self.skipTest("Tkinter display environment unavailable")

    def tearDown(self):
        if hasattr(self, "app") and self.app:
            try:
                self.app.destroy()
            except Exception:
                pass

    def test_gui_initialization_and_title(self):
        self.assertIn("MTGNP", self.app.title())
        self.assertIsNotNone(self.app.opp_header_lbl)
        self.assertIsNotNone(self.app.local_header_lbl)

    def test_authoritative_state_rendering_in_gui(self):
        state_pdu = {
            "type": "GAME_STATE_UPDATE",
            "seq_num": 1,
            "state": {
                "turn": 3,
                "phase": "PRECOMBAT_MAIN",
                "active_player": "player_1",
                "priority_holder": "player_1",
                "life_totals": {"player_1": 20, "player_2": 17},
                "library_counts": {"player_1": 40, "player_2": 40},
                "hand": ["lightning_bolt_001", "mountain_001"],
                "hand_counts": {"player_2": 5},
                "graveyard": {"player_1": [], "player_2": ["shock_001"]},
                "battlefield": {
                    "player_1": [{"id": "mountain_001", "tapped": False}],
                    "player_2": [{"id": "grizzly_bears_001", "tapped": True, "power": 2, "toughness": 2, "damage": 0}]
                },
                "stack": [
                    {"stack_item_id": "stk_01", "source": "lightning_bolt_001", "controller": "player_1", "targets": ["player_2"]}
                ]
            }
        }

        self.app.enqueue_pdu(state_pdu)
        self.app._process_queue()

        opp_text = self.app.opp_header_lbl.cget("text")
        self.assertIn("Life 17", opp_text)
        self.assertIn("Hand Cards: 5", opp_text)

        local_text = self.app.local_header_lbl.cget("text")
        self.assertIn("Life 20", local_text)

        stack_count = self.app.stack_listbox.size()
        self.assertEqual(stack_count, 1)
        self.assertIn("lightning_bolt_001", self.app.stack_listbox.get(0))

    def test_action_buttons_send_correct_pdus(self):
        self.client_state.last_seq_num = 15
        self.client_state.player_id = "player_1"

        self.app._on_pass_click()
        self.assertEqual(len(self.sent_pdus), 1)
        self.assertEqual(self.sent_pdus[0], {"type": "PRIORITY_PASS", "seq_num": 15})

        self.app.selected_card_id = "mountain_001"
        self.app._on_play_land_click()
        self.assertEqual(len(self.sent_pdus), 2)
        self.assertEqual(self.sent_pdus[1], {"type": "PLAY_LAND", "seq_num": 15, "card_id": "mountain_001"})

    @patch("tkinter.messagebox.showerror")
    def test_error_pdu_rendering(self, mock_error):
        err_pdu = {
            "type": "ERROR",
            "seq_num": 16,
            "code": "STALE_ACTION",
            "message": "Sequence number mismatch."
        }
        self.app.enqueue_pdu(err_pdu)
        self.app._process_queue()

        log_content = self.app.log_text.get("1.0", tk.END)
        self.assertIn("STALE_ACTION", log_content)
        mock_error.assert_called_once()

if __name__ == "__main__":
    unittest.main()
