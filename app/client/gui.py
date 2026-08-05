import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Dict, Any, List, Optional, Callable
import queue
import json
from app.client.__main__ import ClientState
from app.server.game.cards import CardCatalog

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
        self.geometry("1100x820")
        self.minsize(950, 650)
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
        self.after(100, self._process_queue)

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

        # 2. Center Split (Left: Stack, Center: Board, Right: Log)
        self.center_frame = ttk.Frame(self.main_container, style="TFrame")
        self.center_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Center Left: Stack Panel
        self.stack_panel = ttk.Frame(self.center_frame, style="Panel.TFrame", padding=6, width=230)
        self.stack_panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))
        self.stack_panel.pack_propagate(False)

        ttk.Label(self.stack_panel, text="The Stack (LIFO)", style="Header.TLabel", background=self.PANEL_BG).pack(anchor=tk.W)
        self.stack_listbox = tk.Listbox(self.stack_panel, bg=self.CARD_BG, fg=self.TEXT_COLOR, selectbackground=self.ACCENT_BLUE, bd=0, highlightthickness=0, font=("Consolas", 9))
        self.stack_listbox.pack(fill=tk.BOTH, expand=True, pady=5)

        # Center Main: Status & Shared Board
        self.board_panel = ttk.Frame(self.center_frame, style="Panel.TFrame", padding=6)
        self.board_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)

        self.status_bar = ttk.Label(self.board_panel, text="Turn: 0 | Phase: LOBBY | Active: - | Priority: -", style="Status.TLabel", background=self.PANEL_BG)
        self.status_bar.pack(anchor=tk.W, pady=(0, 5))

        self.battlefield_label = ttk.Label(self.board_panel, text="Battlefield Permanents", style="Header.TLabel", background=self.PANEL_BG)
        self.battlefield_label.pack(anchor=tk.W)

        self.shared_battlefield_frame = ttk.Frame(self.board_panel, style="Panel.TFrame")
        self.shared_battlefield_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Center Right: Log Panel
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

        # Hand Container
        ttk.Label(self.local_panel, text="Your Hand (Click to select card)", style="Header.TLabel", background=self.PANEL_BG).pack(anchor=tk.W, pady=(5, 2))
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
        self.after(100, self._process_queue)

    def _handle_pdu(self, pdu: Dict[str, Any]):
        self.client_state.update_authoritative_state(pdu)
        ptype = pdu.get("type")
        if ptype == "GAME_STATE_UPDATE":
            st = self.client_state.current_state
            self.log_event(f"State Update: Turn {st.get('turn')} | Phase: {st.get('phase')}")
        elif ptype == "PHASE_TRANSITION":
            self.log_event(f"Phase -> {pdu.get('to_phase')} (Active: {pdu.get('active_player')})")
        elif ptype == "STACK_PUSH":
            self.log_event(f"Stack Push: {pdu.get('source')} by {pdu.get('controller')}")
        elif ptype == "STACK_RESOLVE":
            self.log_event(f"Stack Resolve: {pdu.get('stack_item_id')} -> {pdu.get('result')}")
        elif ptype == "ERROR":
            self.log_event(f"ERROR [{pdu.get('code')}]: {pdu.get('message')}")
            messagebox.showerror(f"Error ({pdu.get('code')})", pdu.get('message', 'Illegal Action'))

        self.render_state()

    def render_state(self):
        st = self.client_state.current_state
        if not st:
            return

        # Status Bar
        self.status_bar.config(
            text=f"Turn: {st.get('turn', 0)} | Phase: {st.get('phase', 'LOBBY')} | Active: {st.get('active_player', '-')} | Priority: {st.get('priority_holder', '-')}"
        )

        lifes = st.get("life_totals", {})
        libs = st.get("library_counts", {})
        gys = st.get("graveyard", {})
        h_counts = st.get("hand_counts", {})

        local_p = self.client_state.player_id or "player_1"
        opp_p = [p for p in lifes.keys() if p != local_p]
        opp_id = opp_p[0] if opp_p else "Opponent"

        # Header Labels
        self.opp_header_lbl.config(
            text=f"Opponent ({opp_id}): Life {lifes.get(opp_id, 20)} | Hand Cards: {h_counts.get(opp_id, 0)} | Library: {libs.get(opp_id, 0)} | GY: {len(gys.get(opp_id, []))}"
        )

        self.local_header_lbl.config(
            text=f"You ({local_p}): Life {lifes.get(local_p, 20)} | Library {libs.get(local_p, 0)} | GY {len(gys.get(local_p, []))}"
        )

        # Render Opponent Battlefield
        for w in self.opp_battlefield_frame.winfo_children():
            w.destroy()
        opp_perms = st.get("battlefield", {}).get(opp_id, [])
        for perm in opp_perms:
            self._create_permanent_card(self.opp_battlefield_frame, perm, is_opponent=True)

        # Render Local Battlefield
        for w in self.shared_battlefield_frame.winfo_children():
            w.destroy()
        local_perms = st.get("battlefield", {}).get(local_p, [])
        for perm in local_perms:
            self._create_permanent_card(self.shared_battlefield_frame, perm, is_opponent=False)

        # Render Local Hand
        for w in self.hand_container.winfo_children():
            w.destroy()
        hand_cards = st.get("hand", [])
        for card_id in hand_cards:
            self._create_hand_card(self.hand_container, card_id)

        # Render Stack
        self.stack_listbox.delete(0, tk.END)
        stk = st.get("stack", [])
        for idx, item in enumerate(stk):
            self.stack_listbox.insert(tk.END, f"[{idx}] {item.get('source')} ({item.get('item_type')}) -> {item.get('targets')}")

        # Priority Control Enabling
        has_priority = (st.get("priority_holder") == local_p)
        if has_priority:
            self.pass_btn.config(state=tk.NORMAL)
            self.play_land_btn.config(state=tk.NORMAL)
            self.cast_spell_btn.config(state=tk.NORMAL)
            self.action_status_lbl.config(text="YOUR PRIORITY", foreground=self.ACCENT_GREEN)
        else:
            self.pass_btn.config(state=tk.DISABLED)
            self.play_land_btn.config(state=tk.DISABLED)
            self.cast_spell_btn.config(state=tk.DISABLED)
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

        # Accent Bar
        bar = tk.Frame(card_frame, bg=accent_color, height=3)
        bar.pack(fill=tk.X, pady=(0, 3))

        # Title & Cost
        lbl_title = tk.Label(card_frame, text=name, bg=bg_col, fg=self.TEXT_COLOR, font=("Segoe UI", 9, "bold"))
        lbl_title.pack(anchor=tk.W)

        lbl_sub = tk.Label(card_frame, text=f"{card_type} ({cmc})", bg=bg_col, fg=self.MUTED_TEXT, font=("Segoe UI", 8))
        lbl_sub.pack(anchor=tk.W)

        if def_obj and def_obj.is_creature():
            pt_str = f"{def_obj.power}/{def_obj.toughness}"
            lbl_pt = tk.Label(card_frame, text=pt_str, bg=bg_col, fg=self.ACCENT_YELLOW, font=("Segoe UI", 9, "bold"))
            lbl_pt.pack(anchor=tk.E)

        # Bind click selection
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

        bg_col = "#2a2b3c" if not is_opponent else "#212230"
        border_col = self.ACCENT_RED if tapped else self.ACCENT_BLUE

        perm_frame = tk.Frame(parent, bg=bg_col, bd=2, relief=tk.GROOVE, padx=6, pady=4)
        perm_frame.pack(side=tk.LEFT, padx=4, pady=2)

        status_str = "[TAPPED]" if tapped else "[READY]"
        lbl_status = tk.Label(perm_frame, text=status_str, bg=bg_col, fg=border_col, font=("Segoe UI", 8, "bold"))
        lbl_status.pack(anchor=tk.W)

        lbl_name = tk.Label(perm_frame, text=name, bg=bg_col, fg=self.TEXT_COLOR, font=("Segoe UI", 9, "bold"))
        lbl_name.pack(anchor=tk.W)

        if "power" in perm:
            pt_str = f"P/T: {perm.get('power')}/{perm.get('toughness')} (Dmg: {perm.get('damage', 0)})"
            lbl_pt = tk.Label(perm_frame, text=pt_str, bg=bg_col, fg=self.ACCENT_YELLOW, font=("Segoe UI", 8))
            lbl_pt.pack(anchor=tk.W)
            if perm.get("summoning_sick"):
                lbl_sick = tk.Label(perm_frame, text="*Sick*", bg=bg_col, fg=self.MUTED_TEXT, font=("Segoe UI", 7, "italic"))
                lbl_sick.pack(anchor=tk.E)

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

    def _on_concede_click(self):
        if messagebox.askyesno("Concede", "Are you sure you want to concede the game?"):
            if self.send_action_fn:
                pdu = self.client_state.build_concede(self.client_state.player_id or "player_1")
                self.send_action_fn(pdu)
                self.log_event("Sent: Concede")

if __name__ == "__main__":
    app = GraphicalGameClient()
    app.mainloop()
