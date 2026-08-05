"""
MTGNP Graphical Desktop Client UI implementation built with Python tkinter.
Reuses the authoritative client state store, TCP socket connection, and framed PDU serializer.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Dict, Any, List, Optional, Callable
import queue
import json
from app.client.state import ClientState
from app.shared.cards import CardCatalog
from app.client.actions import ClientActionFactory

class GraphicalGameClient(tk.Tk):
    BG_DARK = "#1e1e2e"
    PANEL_BG = "#181825"
    CARD_BG = "#313244"
    CARD_SELECTED_BG = "#45475a"
    TEXT_COLOR = "#cdd6f4"
    ACCENT_BLUE = "#89b4fa"
    ACCENT_GREEN = "#a6e3a1"
    ACCENT_RED = "#f38ba8"
    ACCENT_YELLOW = "#f9e2af"
    MUTED_TEXT = "#a6adc8"

    COLOR_ACCENTS = {
        "W": "#f5e0dc",
        "U": "#89b4fa",
        "B": "#585b70",
        "R": "#f38ba8",
        "G": "#a6e3a1",
        "C": "#9399b2"
    }

    def __init__(self, client_state: Optional[ClientState] = None, send_action_fn: Optional[Callable[[Dict[str, Any]], None]] = None):
        super().__init__()
        self.title("MTGNP - Magic: The Gathering Network Protocol")
        self.geometry("1100x840")
        self.minsize(950, 680)
        self.configure(bg=self.BG_DARK)

        self.client_state = client_state or ClientState()
        self.send_action_fn = send_action_fn
        self.queue: queue.Queue = queue.Queue()
        self.catalog = CardCatalog.get_instance()

        self.selected_card_id: Optional[str] = None
        self.selected_permanent_id: Optional[str] = None
        self.selected_attackers: List[str] = []
        self.selected_blockers: List[Dict[str, str]] = []

        self._init_ui_shell()
        self._after_id = self.after(100, self._process_queue)

    def destroy(self):
        if hasattr(self, "_after_id") and self._after_id:
            try:
                self.after_cancel(self._after_id)
            except Exception:
                pass
        super().destroy()

    def _init_ui_shell(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background=self.BG_DARK)
        style.configure("Panel.TFrame", background=self.PANEL_BG)
        style.configure("TLabel", background=self.BG_DARK, foreground=self.TEXT_COLOR, font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 11, "bold"), foreground=self.ACCENT_BLUE)
        style.configure("Status.TLabel", font=("Segoe UI", 10, "bold"), foreground=self.ACCENT_YELLOW)

        self.main_container = ttk.Frame(self, style="TFrame")
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 1. Opponent Area
        self.opp_panel = ttk.Frame(self.main_container, style="Panel.TFrame", padding=8)
        self.opp_panel.pack(fill=tk.X, side=tk.TOP, pady=(0, 5))

        self.opp_header_lbl = ttk.Label(self.opp_panel, text="Opponent: [Waiting...] | Life: 20 | Hand: 0 | Library: 0 | GY: 0", style="Header.TLabel", background=self.PANEL_BG)
        self.opp_header_lbl.pack(anchor=tk.W)

        self.opp_battlefield_frame = ttk.Frame(self.opp_panel, style="Panel.TFrame")
        self.opp_battlefield_frame.pack(fill=tk.X, expand=True, pady=5)

        # 2. Center Split
        self.center_frame = ttk.Frame(self.main_container, style="TFrame")
        self.center_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Stack Panel
        self.stack_panel = ttk.Frame(self.center_frame, style="Panel.TFrame", padding=6, width=230)
        self.stack_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        self.stack_panel.pack_propagate(False)

        ttk.Label(self.stack_panel, text="The Stack (LIFO)", style="Header.TLabel", background=self.PANEL_BG).pack(anchor=tk.W)
        self.stack_listbox = tk.Listbox(self.stack_panel, bg=self.CARD_BG, fg=self.TEXT_COLOR, selectbackground=self.ACCENT_BLUE, bd=0, highlightthickness=0, font=("Consolas", 9))
        self.stack_listbox.pack(fill=tk.BOTH, expand=True, pady=5)

        # Board Panel
        self.board_panel = ttk.Frame(self.center_frame, style="Panel.TFrame", padding=6)
        self.board_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        self.status_bar = ttk.Label(self.board_panel, text="Turn: 0 | Phase: LOBBY | Active: - | Priority: -", style="Status.TLabel", background=self.PANEL_BG)
        self.status_bar.pack(anchor=tk.W, pady=(0, 5))

        self.battlefield_label = ttk.Label(self.board_panel, text="Battlefield Permanents", style="Header.TLabel", background=self.PANEL_BG)
        self.battlefield_label.pack(anchor=tk.W)

        self.shared_battlefield_frame = ttk.Frame(self.board_panel, style="Panel.TFrame")
        self.shared_battlefield_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Log Panel
        self.log_panel = ttk.Frame(self.center_frame, style="Panel.TFrame", padding=6, width=280)
        self.log_panel.pack(side=tk.RIGHT, fill=tk.Y, padx=(5, 0))
        self.log_panel.pack_propagate(False)

        ttk.Label(self.log_panel, text="Game Event Log", style="Header.TLabel", background=self.PANEL_BG).pack(anchor=tk.W)
        self.log_text = tk.Text(self.log_panel, bg=self.CARD_BG, fg=self.TEXT_COLOR, bd=0, highlightthickness=0, wrap=tk.WORD, font=("Consolas", 8), state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=5)

        # 3. Local Player Area
        self.local_panel = ttk.Frame(self.main_container, style="Panel.TFrame", padding=8)
        self.local_panel.pack(fill=tk.X, side=tk.BOTTOM, pady=(5, 0))

        self.local_header_lbl = ttk.Label(self.local_panel, text="You (Local): [Waiting...] | Life: 20 | Library: 0 | GY: 0", style="Header.TLabel", background=self.PANEL_BG)
        self.local_header_lbl.pack(anchor=tk.W)

        # Hand Frame
        ttk.Label(self.local_panel, text="Your Hand (Click card to select)", style="Header.TLabel", background=self.PANEL_BG).pack(anchor=tk.W, pady=(5, 2))
        self.hand_container = ttk.Frame(self.local_panel, style="Panel.TFrame")
        self.hand_container.pack(fill=tk.X, expand=True, pady=2)

        # Action Bar
        self.action_bar = ttk.Frame(self.local_panel, style="Panel.TFrame")
        self.action_bar.pack(fill=tk.X, pady=(5, 0))

        self.pass_btn = tk.Button(self.action_bar, text="Pass Priority", bg=self.ACCENT_BLUE, fg="#000000", font=("Segoe UI", 9, "bold"), command=self._on_pass_click)
        self.pass_btn.pack(side=tk.LEFT, padx=3)

        self.play_land_btn = tk.Button(self.action_bar, text="Play Land", bg=self.ACCENT_GREEN, fg="#000000", font=("Segoe UI", 9, "bold"), command=self._on_play_land_click)
        self.play_land_btn.pack(side=tk.LEFT, padx=3)

        self.cast_spell_btn = tk.Button(self.action_bar, text="Cast Spell", bg=self.ACCENT_YELLOW, fg="#000000", font=("Segoe UI", 9, "bold"), command=self._on_cast_spell_click)
        self.cast_spell_btn.pack(side=tk.LEFT, padx=3)

        self.activate_ability_btn = tk.Button(self.action_bar, text="Activate Ability", bg=self.ACCENT_BLUE, fg="#000000", font=("Segoe UI", 9, "bold"), command=self._on_activate_ability_click)
        self.activate_ability_btn.pack(side=tk.LEFT, padx=3)

        self.attack_btn = tk.Button(self.action_bar, text="Confirm Attackers", bg=self.ACCENT_RED, fg="#ffffff", font=("Segoe UI", 9, "bold"), command=self._on_confirm_attackers_click)
        self.attack_btn.pack(side=tk.LEFT, padx=3)

        self.block_btn = tk.Button(self.action_bar, text="Confirm Blockers", bg=self.ACCENT_RED, fg="#ffffff", font=("Segoe UI", 9, "bold"), command=self._on_confirm_blockers_click)
        self.block_btn.pack(side=tk.LEFT, padx=3)

        self.concede_btn = tk.Button(self.action_bar, text="Concede", bg=self.ACCENT_RED, fg="#ffffff", font=("Segoe UI", 9, "bold"), command=self._on_concede_click)
        self.concede_btn.pack(side=tk.RIGHT, padx=3)

        self.action_status_lbl = ttk.Label(self.action_bar, text="Action status: Ready", style="TLabel", background=self.PANEL_BG)
        self.action_status_lbl.pack(side=tk.LEFT, padx=10)

    def log_event(self, msg: str):
        self.log_text.config(state=tk.NORMAL)
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.config(state=tk.DISABLED)

    def enqueue_pdu(self, pdu: Dict[str, Any]):
        self.queue.put(pdu)

    def _process_queue(self):
        while not self.queue.empty():
            pdu = self.queue.get_nowait()
            self._handle_pdu(pdu)
        if self._after_id is not None:
            self._after_id = self.after(100, self._process_queue)

    def _handle_pdu(self, pdu: Dict[str, Any]):
        self.client_state.update_authoritative_state(pdu)
        ptype = pdu.get("type")
        if ptype in ("MATCH_START", "PLAYER_ASSIGNMENT"):
            pid = pdu.get("player_id", "")
            if pid:
                self.client_state.player_id = pid
            self.log_event(f"Match Connected: You are {self.client_state.player_id or 'Player'}")
        elif ptype == "GAME_STATE_UPDATE":
            st = self.client_state.current_state
            self.log_event(f"State Update: Turn {st.get('turn')} | Phase: {st.get('phase')}")
        elif ptype == "PHASE_TRANSITION":
            self.log_event(f"Phase -> {pdu.get('to_phase')} (Active: {pdu.get('active_player')})")
        elif ptype == "STACK_PUSH":
            self.log_event(f"Stack Push: {pdu.get('source')} by {pdu.get('controller')}")
        elif ptype == "STACK_RESOLVE":
            self.log_event(f"Stack Resolve: {pdu.get('stack_item_id')} -> {pdu.get('result')}")
        elif ptype == "MULLIGAN_PROMPT":
            self._show_mulligan_dialog(pdu)
        elif ptype == "TRIGGER_CHOICE":
            self._show_trigger_choice_dialog(pdu)
        elif ptype == "DISCARD_PROMPT":
            self._show_discard_dialog(pdu)
        elif ptype == "GAME_OVER":
            self.log_event(f"GAME OVER: Winner {pdu.get('winner_id')} ({pdu.get('reason')})")
            messagebox.showinfo("Game Over", f"Game Over!\nWinner: {pdu.get('winner_id')}\nReason: {pdu.get('reason')}")
        elif ptype == "ERROR":
            self.log_event(f"ERROR [{pdu.get('code')}]: {pdu.get('message')}")
            messagebox.showerror(f"Error ({pdu.get('code')})", pdu.get('message', 'Illegal Action'))

        self.render_state()

    def _show_mulligan_dialog(self, pdu: Dict[str, Any]):
        keep = messagebox.askyesno("Mulligan", "Do you want to KEEP your opening hand? (No = Mulligan)")
        if self.send_action_fn:
            action = {"type": "MULLIGAN_CHOICE", "seq_num": self.client_state.last_seq_num, "keep": keep}
            self.send_action_fn(action)
            self.log_event(f"Sent Mulligan Choice: Keep={keep}")

    def _show_trigger_choice_dialog(self, pdu: Dict[str, Any]):
        trg_id = pdu.get("trigger_id", "")
        accept = messagebox.askyesno("Triggered Ability", f"Optional Trigger ({trg_id}):\n{pdu.get('summary', '')}\nDo you accept?")
        if self.send_action_fn:
            action = self.client_state.build_trigger_choice_response(trg_id, accept)
            self.send_action_fn(action)
            self.log_event(f"Sent Trigger Choice ({trg_id}): Accept={accept}")

    def _show_discard_dialog(self, pdu: Dict[str, Any]):
        count = pdu.get("count", 1)
        cards_str = simpledialog.askstring("Discard Required", f"Discard {count} card ID(s) (comma-separated):")
        to_discard = [c.strip() for c in cards_str.split(",")] if cards_str else []
        if self.send_action_fn:
            action = self.client_state.build_discard(to_discard)
            self.send_action_fn(action)
            self.log_event(f"Sent Discard: {to_discard}")

    def render_state(self):
        st = self.client_state.current_state
        if not st:
            return

        self.status_bar.config(
            text=f"Turn: {st.get('turn', 0)} | Phase: {st.get('phase', 'LOBBY')} | Active: {st.get('active_player', '-')} | Priority: {st.get('priority_holder', '-')}"
        )

        lifes = st.get("life_totals", {})
        libs = st.get("library_counts", {})
        gys = st.get("graveyard", {})
        h_counts = st.get("hand_counts", {})

        local_p = self.client_state.player_id or "player_1"
        opp_p = [p for p in lifes.keys() if p != local_p]
        opp_id = opp_p[0] if opp_p else ("player_2" if local_p == "player_1" else "player_1")

        self.opp_header_lbl.config(
            text=f"Opponent ({opp_id}): Life {lifes.get(opp_id, 20)} | Hand Cards: {h_counts.get(opp_id, 0)} | Library: {libs.get(opp_id, 0)} | GY: {len(gys.get(opp_id, []))}"
        )

        self.local_header_lbl.config(
            text=f"You ({local_p}): Life {lifes.get(local_p, 20)} | Library {libs.get(local_p, 0)} | GY {len(gys.get(local_p, []))}"
        )

        for w in self.opp_battlefield_frame.winfo_children():
            w.destroy()
        opp_perms = st.get("battlefield", {}).get(opp_id, [])
        for perm in opp_perms:
            self._create_permanent_card(self.opp_battlefield_frame, perm, is_opponent=True)

        for w in self.shared_battlefield_frame.winfo_children():
            w.destroy()
        local_perms = st.get("battlefield", {}).get(local_p, [])
        for perm in local_perms:
            self._create_permanent_card(self.shared_battlefield_frame, perm, is_opponent=False)

        for w in self.hand_container.winfo_children():
            w.destroy()
        hand_cards = st.get("hand", [])
        for card_id in hand_cards:
            self._create_hand_card(self.hand_container, card_id)

        self.stack_listbox.delete(0, tk.END)
        stk = st.get("stack", [])
        for idx, item in enumerate(stk):
            self.stack_listbox.insert(tk.END, f"[{idx}] {item.get('source')} ({item.get('item_type')}) -> {item.get('targets')}")

        has_priority = (st.get("priority_holder") == local_p)
        phase = st.get("phase", "")

        if phase == "DECLARE_ATTACKERS" and st.get("active_player") == local_p:
            self.attack_btn.config(state=tk.NORMAL)
            self.block_btn.config(state=tk.DISABLED)
        elif phase == "DECLARE_BLOCKERS" and st.get("active_player") != local_p:
            self.attack_btn.config(state=tk.DISABLED)
            self.block_btn.config(state=tk.NORMAL)
        else:
            self.attack_btn.config(state=tk.DISABLED)
            self.block_btn.config(state=tk.DISABLED)

        if has_priority:
            self.pass_btn.config(state=tk.NORMAL)
            self.play_land_btn.config(state=tk.NORMAL)
            self.cast_spell_btn.config(state=tk.NORMAL)
            self.activate_ability_btn.config(state=tk.NORMAL)
            self.action_status_lbl.config(text="YOUR PRIORITY", foreground=self.ACCENT_GREEN)
        else:
            self.pass_btn.config(state=tk.DISABLED)
            self.play_land_btn.config(state=tk.DISABLED)
            self.cast_spell_btn.config(state=tk.DISABLED)
            self.activate_ability_btn.config(state=tk.DISABLED)
            self.action_status_lbl.config(text=f"Waiting for {st.get('priority_holder', 'opponent')}...", foreground=self.MUTED_TEXT)

    def _create_hand_card(self, parent: tk.Widget, card_id: str):
        def_obj = self.catalog.get_definition(card_id)
        name = def_obj.name if def_obj else card_id
        color = def_obj.color if def_obj else "C"
        cmc = def_obj.cmc if def_obj else 0
        card_type = def_obj.card_type if def_obj else "Unknown"

        accent_color = self.COLOR_ACCENTS.get(color, self.CARD_BG)
        is_selected = (self.selected_card_id == card_id)
        bg_col = self.CARD_SELECTED_BG if is_selected else self.CARD_BG

        card_frame = tk.Frame(parent, bg=bg_col, bd=2, relief=tk.RAISED if is_selected else tk.FLAT, padx=6, pady=4, cursor="hand2")
        card_frame.pack(side=tk.LEFT, padx=4, pady=2)

        bar = tk.Frame(card_frame, bg=accent_color, height=3)
        bar.pack(fill=tk.X, pady=(0, 3))

        lbl_title = tk.Label(card_frame, text=name, bg=bg_col, fg=self.TEXT_COLOR, font=("Segoe UI", 9, "bold"))
        lbl_title.pack(anchor=tk.W)

        lbl_sub = tk.Label(card_frame, text=f"{card_type} ({cmc})", bg=bg_col, fg=self.MUTED_TEXT, font=("Segoe UI", 8))
        lbl_sub.pack(anchor=tk.W)

        if def_obj and def_obj.is_creature():
            pt_str = f"{def_obj.power}/{def_obj.toughness}"
            lbl_pt = tk.Label(card_frame, text=pt_str, bg=bg_col, fg=self.ACCENT_YELLOW, font=("Segoe UI", 9, "bold"))
            lbl_pt.pack(anchor=tk.E)

        def select_card(e):
            self.selected_card_id = card_id
            self.render_state()

        card_frame.bind("<Button-1>", select_card)
        lbl_title.bind("<Button-1>", select_card)

    def _create_permanent_card(self, parent: tk.Widget, perm: Dict[str, Any], is_opponent: bool):
        cid = perm.get("id", "")
        def_obj = self.catalog.get_definition(cid)
        name = def_obj.name if def_obj else cid
        tapped = perm.get("tapped", False)

        is_attacker = cid in self.selected_attackers
        is_selected = (self.selected_permanent_id == cid)
        bg_col = self.ACCENT_RED if is_attacker else (self.CARD_SELECTED_BG if is_selected else ("#2a2b3c" if not is_opponent else "#212230"))
        fg_col = "#000000" if is_attacker else self.TEXT_COLOR
        border_col = self.ACCENT_RED if tapped else self.ACCENT_BLUE

        perm_frame = tk.Frame(parent, bg=bg_col, bd=2, relief=tk.RAISED if is_selected else tk.GROOVE, padx=6, pady=4, cursor="hand2")
        perm_frame.pack(side=tk.LEFT, padx=4, pady=2)

        status_str = "[ATTACKING]" if is_attacker else ("[TAPPED]" if tapped else "[READY]")
        lbl_status = tk.Label(perm_frame, text=status_str, bg=bg_col, fg=border_col, font=("Segoe UI", 8, "bold"))
        lbl_status.pack(anchor=tk.W)

        lbl_name = tk.Label(perm_frame, text=name, bg=bg_col, fg=fg_col, font=("Segoe UI", 9, "bold"))
        lbl_name.pack(anchor=tk.W)

        if "power" in perm:
            pt_str = f"P/T: {perm.get('power')}/{perm.get('toughness')} (Dmg: {perm.get('damage', 0)})"
            lbl_pt = tk.Label(perm_frame, text=pt_str, bg=bg_col, fg=self.ACCENT_YELLOW, font=("Segoe UI", 8))
            lbl_pt.pack(anchor=tk.W)
            if perm.get("summoning_sick"):
                lbl_sick = tk.Label(perm_frame, text="*Sick*", bg=bg_col, fg=self.MUTED_TEXT, font=("Segoe UI", 7, "italic"))
                lbl_sick.pack(anchor=tk.E)

        def select_perm(e):
            self.selected_permanent_id = cid
            st = self.client_state.current_state
            if st.get("phase") == "DECLARE_ATTACKERS" and not is_opponent:
                if cid in self.selected_attackers:
                    self.selected_attackers.remove(cid)
                else:
                    self.selected_attackers.append(cid)
            self.render_state()

        perm_frame.bind("<Button-1>", select_perm)
        lbl_name.bind("<Button-1>", select_perm)

    def _on_pass_click(self):
        if self.send_action_fn:
            pdu = self.client_state.build_priority_pass()
            self.send_action_fn(pdu)
            self.log_event("Sent: Priority Pass")

    def _on_play_land_click(self):
        if not self.selected_card_id:
            messagebox.showinfo("Select Card", "Please select a land card from your hand first.")
            return
        if self.send_action_fn:
            pdu = self.client_state.build_play_land(self.selected_card_id)
            self.send_action_fn(pdu)
            self.log_event(f"Sent: Play Land ({self.selected_card_id})")

    def _on_cast_spell_click(self):
        if not self.selected_card_id:
            messagebox.showinfo("Select Card", "Please select a spell from your hand first.")
            return
        def_obj = self.catalog.get_definition(self.selected_card_id)
        if not def_obj:
            return

        target_input = simpledialog.askstring("Targets", f"Target ID(s) for {def_obj.name} (comma-separated, leave blank if none):")
        targets = [t.strip() for t in target_input.split(",")] if target_input else []
        mana_payment = dict(def_obj.mana_cost)

        if self.send_action_fn:
            pdu = self.client_state.build_cast_spell(self.selected_card_id, targets, mana_payment)
            self.send_action_fn(pdu)
            self.log_event(f"Sent: Cast Spell ({self.selected_card_id})")

    def _on_activate_ability_click(self):
        if not self.selected_permanent_id:
            messagebox.showinfo("Select Permanent", "Please select a permanent on your battlefield first.")
            return

        target_input = simpledialog.askstring("Ability Target", f"Target ID for ability on {self.selected_permanent_id} (leave blank if none):")
        targets = [target_input.strip()] if target_input else []

        if self.send_action_fn:
            pdu = self.client_state.build_activate_ability(self.selected_permanent_id, 0, targets, {"tap": True})
            self.send_action_fn(pdu)
            self.log_event(f"Sent: Activate Ability on ({self.selected_permanent_id})")

    def _on_confirm_attackers_click(self):
        st = self.client_state.current_state
        local_p = self.client_state.player_id or "player_1"
        opp_target = [p for p in st.get("life_totals", {}).keys() if p != local_p]
        target_p = opp_target[0] if opp_target else "player_2"

        declarations = [{"creature_id": cid, "target": target_p} for cid in self.selected_attackers]
        if self.send_action_fn:
            pdu = self.client_state.build_declare_attackers(declarations)
            self.send_action_fn(pdu)
            self.log_event(f"Sent: Declare Attackers ({declarations})")
            self.selected_attackers.clear()

    def _on_confirm_blockers_click(self):
        if self.send_action_fn:
            pdu = self.client_state.build_declare_blockers(self.selected_blockers)
            self.send_action_fn(pdu)
            self.log_event(f"Sent: Declare Blockers ({self.selected_blockers})")
            self.selected_blockers.clear()

    def _on_concede_click(self):
        if messagebox.askyesno("Concede", "Are you sure you want to concede the game?"):
            if self.send_action_fn:
                pdu = self.client_state.build_concede()
                self.send_action_fn(pdu)
                self.log_event("Sent: Concede")

if __name__ == "__main__":
    import socket
    import threading
    from app.client.__main__ import send_framed_pdu, read_framed_pdu

    try:
        host = input("Enter host [127.0.0.1]: ").strip() or "127.0.0.1"
        port_str = input("Enter port [4444]: ").strip() or "4444"
        port = int(port_str)
    except Exception:
        host, port = "127.0.0.1", 4444

    try:
        client_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_sock.connect((host, port))
        print(f"Connected to MTGNP server at {host}:{port}")

        def send_action(pdu: Dict[str, Any]):
            send_framed_pdu(client_sock, pdu)

        app = GraphicalGameClient(send_action_fn=send_action)

        def listen_loop():
            while True:
                try:
                    pdu = read_framed_pdu(client_sock)
                    if not pdu:
                        break
                    app.enqueue_pdu(pdu)
                except Exception:
                    break

        t = threading.Thread(target=listen_loop, daemon=True)
        t.start()

        app.mainloop()
    except Exception as e:
        print(f"Failed to connect or run GUI: {e}")
