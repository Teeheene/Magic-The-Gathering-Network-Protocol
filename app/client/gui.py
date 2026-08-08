"""
MTGNP Graphical Desktop Client UI implementation built with Python tkinter.
Reuses the authoritative client state store, TCP socket connection, and framed PDU serializer.
"""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Dict, Any, List, Optional, Callable, Tuple
import queue
import threading
from app.client.state import ClientState
from app.shared.cards import CardCatalog, validate_deck

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

    def __init__(
        self,
        client_state: Optional[ClientState] = None,
        send_action_fn: Optional[Callable[[Dict[str, Any]], None]] = None,
        connect_fn: Optional[Callable[[str, int, str, List[str]], Tuple[bool, str]]] = None,
        disconnect_fn: Optional[Callable[[], None]] = None,
        initial_host: str = "127.0.0.1",
        initial_port: int = 4444,
        initial_player_id: str = "",
    ):
        super().__init__()
        self.title("MTGNP - Magic: The Gathering Network Protocol")
        self.geometry("1100x840")
        self.minsize(950, 680)
        self.configure(bg=self.BG_DARK)

        self.client_state = client_state or ClientState(player_id="player_1")
        self.send_action_fn = send_action_fn
        self.connect_fn = connect_fn
        self.disconnect_fn = disconnect_fn
        self.initial_host = initial_host
        self.initial_port = initial_port
        self.initial_player_id = initial_player_id
        self.queue: queue.Queue = queue.Queue()
        self.catalog = CardCatalog.get_instance()

        self.selected_card_id: Optional[str] = None
        self.selected_permanent_id: Optional[str] = None
        self.selected_attackers: List[str] = []
        self.selected_blockers: List[Dict[str, str]] = []
        self.selected_block_target: Optional[str] = None
        self._last_mulligan_prompt_seq: Optional[int] = None
        self._last_discard_prompt_seq: Optional[int] = None
        self.selected_setup_cards: List[str] = []
        self.deck_summary_base_ids: List[str] = []

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

        self.screen_container = ttk.Frame(self, style="TFrame")
        self.screen_container.pack(fill=tk.BOTH, expand=True)

        self._build_welcome_screen()

        self.main_container = ttk.Frame(self.screen_container, style="TFrame")

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

        self._show_welcome_screen()

    def _build_welcome_screen(self):
        self.welcome_frame = ttk.Frame(self.screen_container, style="TFrame", padding=36)

        content = ttk.Frame(self.welcome_frame, style="Panel.TFrame", padding=32)
        content.place(relx=0.5, rely=0.5, anchor=tk.CENTER, relwidth=0.86, relheight=0.92)

        self.welcome_title_lbl = tk.Label(
            content,
            text="Magic: The Gathering Network Protocol",
            bg=self.PANEL_BG,
            fg=self.ACCENT_BLUE,
            font=("Segoe UI", 28, "bold"),
        )
        self.welcome_title_lbl.pack(pady=(4, 8))

        connection_panel = tk.Frame(content, bg=self.PANEL_BG)
        connection_panel.pack(fill=tk.X, padx=24, pady=(0, 16))
        connection_panel.grid_columnconfigure(0, weight=3)
        connection_panel.grid_columnconfigure(1, weight=1)
        connection_panel.grid_columnconfigure(2, weight=2)

        fields = (
            ("HOST", "host_entry", self.initial_host),
            ("PORT", "port_entry", str(self.initial_port)),
            ("PLAYER ID", "player_id_entry", self.initial_player_id),
        )
        for column, (label, attribute, value) in enumerate(fields):
            field = tk.Frame(connection_panel, bg=self.PANEL_BG)
            field.grid(row=0, column=column, sticky="ew", padx=5)
            tk.Label(
                field,
                text=label,
                bg=self.PANEL_BG,
                fg=self.MUTED_TEXT,
                font=("Segoe UI", 8, "bold"),
            ).pack(anchor=tk.W, pady=(0, 4))
            entry = tk.Entry(
                field,
                bg=self.CARD_BG,
                fg=self.TEXT_COLOR,
                insertbackground=self.TEXT_COLOR,
                relief=tk.FLAT,
                font=("Segoe UI", 10),
            )
            entry.insert(0, value)
            entry.pack(fill=tk.X, ipady=7)
            setattr(self, attribute, entry)

        self.connection_status_lbl = tk.Label(
            content,
            text="Enter a unique player ID to join.",
            bg=self.PANEL_BG,
            fg=self.MUTED_TEXT,
            font=("Segoe UI", 9),
        )
        self.connection_status_lbl.pack(pady=(0, 10))

        picker_panel = tk.Frame(
            content,
            bg=self.BG_DARK,
            highlightbackground=self.CARD_SELECTED_BG,
            highlightthickness=1,
            padx=16,
            pady=14,
        )
        picker_panel.pack(fill=tk.X, padx=24)

        picker_header = tk.Frame(picker_panel, bg=self.BG_DARK)
        picker_header.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            picker_header,
            text="BUILD YOUR DECK",
            bg=self.BG_DARK,
            fg=self.ACCENT_YELLOW,
            font=("Segoe UI", 11, "bold"),
        ).pack(side=tk.LEFT)
        self.setup_selection_lbl = tk.Label(
            picker_header,
            text="0 / 50 cards",
            bg=self.BG_DARK,
            fg=self.MUTED_TEXT,
            font=("Segoe UI", 9),
        )
        self.setup_selection_lbl.pack(side=tk.RIGHT)

        preset_row = tk.Frame(picker_panel, bg=self.BG_DARK)
        preset_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            preset_row,
            text="PRESET DECK",
            bg=self.BG_DARK,
            fg=self.MUTED_TEXT,
            font=("Segoe UI", 8, "bold"),
        ).pack(side=tk.LEFT, padx=(0, 8))
        self.preset_decks = self._build_preset_decks()
        self.deck_preset_combo = ttk.Combobox(
            preset_row,
            values=["Custom Deck", *self.preset_decks.keys()],
            state="readonly",
            font=("Segoe UI", 9),
        )
        self.deck_preset_combo.set("Custom Deck")
        self.deck_preset_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.deck_preset_combo.bind("<<ComboboxSelected>>", self._on_preset_selected)

        self.setup_card_panel = tk.Frame(picker_panel, bg=self.BG_DARK)
        self.setup_card_panel.pack(fill=tk.BOTH, expand=True)
        self.setup_card_panel.grid_columnconfigure(0, weight=1)
        self.setup_card_panel.grid_columnconfigure(1, weight=1)

        tk.Label(self.setup_card_panel, text="AVAILABLE CARDS", bg=self.BG_DARK, fg=self.ACCENT_BLUE, font=("Segoe UI", 8, "bold")).grid(row=0, column=0, sticky="w")
        tk.Label(self.setup_card_panel, text="CURRENT DECK", bg=self.BG_DARK, fg=self.ACCENT_GREEN, font=("Segoe UI", 8, "bold")).grid(row=0, column=1, sticky="w", padx=(6, 0))

        self.available_card_ids = sorted(
            self.catalog.definitions,
            key=lambda cid: self.catalog.definitions[cid].name,
        )
        self.available_cards_listbox = tk.Listbox(
            self.setup_card_panel,
            bg=self.CARD_BG,
            fg=self.TEXT_COLOR,
            selectbackground=self.ACCENT_BLUE,
            bd=0,
            highlightthickness=0,
            height=7,
            exportselection=False,
            font=("Segoe UI", 9),
        )
        for base_id in self.available_card_ids:
            definition = self.catalog.definitions[base_id]
            self.available_cards_listbox.insert(tk.END, f"{definition.name}  ·  {definition.card_type}")
        self.available_cards_listbox.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(4, 0))
        self.available_cards_listbox.bind("<Double-Button-1>", lambda _event: self._add_setup_card())

        self.deck_cards_listbox = tk.Listbox(
            self.setup_card_panel,
            bg=self.CARD_BG,
            fg=self.TEXT_COLOR,
            selectbackground=self.ACCENT_GREEN,
            bd=0,
            highlightthickness=0,
            height=7,
            exportselection=False,
            font=("Segoe UI", 9),
        )
        self.deck_cards_listbox.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(4, 0))
        self.deck_cards_listbox.bind("<Double-Button-1>", lambda _event: self._remove_setup_card())

        controls = tk.Frame(self.setup_card_panel, bg=self.BG_DARK)
        controls.grid(row=2, column=0, columnspan=2, pady=(10, 0))
        self.add_card_btn = tk.Button(controls, text="ADD", command=self._add_setup_card, bg=self.ACCENT_BLUE, fg="#11111b", relief=tk.FLAT, font=("Segoe UI", 8, "bold"), padx=12, pady=5)
        self.add_card_btn.pack(side=tk.LEFT, padx=4)
        self.remove_card_btn = tk.Button(controls, text="REMOVE", command=self._remove_setup_card, bg=self.CARD_SELECTED_BG, fg=self.TEXT_COLOR, relief=tk.FLAT, font=("Segoe UI", 8, "bold"), padx=12, pady=5)
        self.remove_card_btn.pack(side=tk.LEFT, padx=4)
        self.clear_deck_btn = tk.Button(controls, text="CLEAR DECK", command=self._clear_setup_deck, bg=self.ACCENT_RED, fg="#ffffff", relief=tk.FLAT, font=("Segoe UI", 8, "bold"), padx=12, pady=5)
        self.clear_deck_btn.pack(side=tk.LEFT, padx=4)

        self.begin_btn = tk.Button(
            content,
            text="ENTER GAME",
            bg=self.ACCENT_GREEN,
            fg="#11111b",
            activebackground="#94e2d5",
            activeforeground="#11111b",
            font=("Segoe UI", 12, "bold"),
            relief=tk.FLAT,
            cursor="hand2",
            padx=24,
            pady=10,
            command=self._on_begin_click,
        )
        self.begin_btn.pack(pady=(24, 2))

    def _build_preset_decks(self) -> Dict[str, List[str]]:
        presets: Dict[str, List[str]] = {}
        color_names = {"R": "Red", "U": "Blue", "G": "Green", "W": "White", "B": "Black"}
        basic_lands = {"R": "mountain", "U": "island", "G": "forest", "W": "plains", "B": "swamp"}
        for color, color_name in color_names.items():
            spells = [
                base_id for base_id, definition in self.catalog.definitions.items()
                if definition.color == color and not definition.is_land()
            ][:5]
            base_cards = [basic_lands[color]] * 20
            for base_id in spells:
                base_cards.extend([base_id] * 4)
            presets[f"{color_name} Starter ({len(base_cards)})"] = self._instance_ids_for(base_cards)
        return presets

    @staticmethod
    def _instance_ids_for(base_cards: List[str]) -> List[str]:
        counts: Dict[str, int] = {}
        instance_ids: List[str] = []
        for base_id in base_cards:
            counts[base_id] = counts.get(base_id, 0) + 1
            instance_ids.append(f"{base_id}_{counts[base_id]:03d}")
        return instance_ids

    def _on_preset_selected(self, _event=None):
        preset_name = self.deck_preset_combo.get()
        if preset_name == "Custom Deck":
            return
        self.selected_setup_cards = list(self.preset_decks[preset_name])
        self._refresh_deck_builder()

    def _add_setup_card(self, base_id: Optional[str] = None):
        if len(self.selected_setup_cards) >= 50:
            self._set_connection_status("A deck cannot contain more than 50 cards.", error=True)
            return
        if base_id is None:
            selection = self.available_cards_listbox.curselection()
            if not selection:
                self._set_connection_status("Select a card from the available-card list first.", error=True)
                return
            base_id = self.available_card_ids[selection[0]]

        used_numbers = {
            int(card_id.rsplit("_", 1)[1])
            for card_id in self.selected_setup_cards
            if self.catalog.extract_base_id(card_id) == base_id and card_id.rsplit("_", 1)[-1].isdigit()
        }
        maximum_copies = self.catalog.definitions[base_id].copies
        if len(used_numbers) >= maximum_copies:
            self._set_connection_status(
                f"The shared catalog contains only {maximum_copies} instance(s) of this card.",
                error=True,
            )
            return
        instance_number = next(number for number in range(1, maximum_copies + 1) if number not in used_numbers)
        self.selected_setup_cards.append(f"{base_id}_{instance_number:03d}")
        self.deck_preset_combo.set("Custom Deck")
        self._refresh_deck_builder()

    def _remove_setup_card(self, base_id: Optional[str] = None):
        if base_id is None:
            selection = self.deck_cards_listbox.curselection()
            if not selection:
                self._set_connection_status("Select a card from the current deck first.", error=True)
                return
            base_id = self.deck_summary_base_ids[selection[0]]
        for index in range(len(self.selected_setup_cards) - 1, -1, -1):
            if self.catalog.extract_base_id(self.selected_setup_cards[index]) == base_id:
                self.selected_setup_cards.pop(index)
                break
        self.deck_preset_combo.set("Custom Deck")
        self._refresh_deck_builder()

    def _clear_setup_deck(self):
        self.selected_setup_cards.clear()
        self.deck_preset_combo.set("Custom Deck")
        self._refresh_deck_builder()
        self._set_connection_status("Deck cleared. Add between 1 and 50 cards.", error=False)

    def _refresh_deck_builder(self):
        counts: Dict[str, int] = {}
        for card_id in self.selected_setup_cards:
            base_id = self.catalog.extract_base_id(card_id)
            counts[base_id] = counts.get(base_id, 0) + 1

        self.deck_cards_listbox.delete(0, tk.END)
        self.deck_summary_base_ids = sorted(counts, key=lambda cid: self.catalog.definitions[cid].name)
        for base_id in self.deck_summary_base_ids:
            definition = self.catalog.definitions[base_id]
            self.deck_cards_listbox.insert(tk.END, f"{counts[base_id]}x  {definition.name}")

        count = len(self.selected_setup_cards)
        valid_count = 1 <= count <= 50
        self.setup_selection_lbl.config(
            text=f"{count} / 50 cards",
            fg=self.ACCENT_GREEN if valid_count else self.ACCENT_RED,
        )

    def _show_welcome_screen(self):
        self.main_container.pack_forget()
        self.welcome_frame.pack(fill=tk.BOTH, expand=True)
        self.current_screen = "welcome"

    def _on_begin_click(self):
        host = self.host_entry.get().strip()
        port_text = self.port_entry.get().strip()
        player_id = self.player_id_entry.get().strip()

        if not host or not port_text or not player_id:
            self._set_connection_status("Host, port, and player ID are required.", error=True)
            return
        try:
            port = int(port_text)
            if not 1 <= port <= 65535:
                raise ValueError
        except ValueError:
            self._set_connection_status("Port must be a number from 1 to 65535.", error=True)
            return

        deck_valid, deck_message = validate_deck(self.selected_setup_cards)
        if not deck_valid:
            self._set_connection_status(deck_message, error=True)
            return

        if self.connect_fn is None:
            self.client_state.player_id = player_id
            self._show_game_screen()
            return

        self.begin_btn.config(state=tk.DISABLED, text="CONNECTING...")
        self._set_connection_status(f"Connecting to {host}:{port}...", error=False)

        def connect_worker():
            try:
                accepted, message = self.connect_fn(
                    host,
                    port,
                    player_id,
                    list(self.selected_setup_cards),
                )
            except Exception as exc:
                accepted, message = False, str(exc)
            self.after(0, lambda: self._finish_connection(accepted, message, player_id))

        threading.Thread(target=connect_worker, daemon=True).start()

    def _finish_connection(self, accepted: bool, message: str, player_id: str):
        self.begin_btn.config(state=tk.NORMAL, text="BEGIN GAME  →")
        if not accepted:
            self._set_connection_status(message or "Connection was rejected.", error=True)
            return
        self.client_state.player_id = player_id
        self._set_connection_status(message or "Connected.", error=False)
        self._show_game_screen()

    def _set_connection_status(self, message: str, error: bool):
        self.connection_status_lbl.config(
            text=message,
            fg=self.ACCENT_RED if error else self.ACCENT_GREEN,
        )

    def _show_game_screen(self):
        self.welcome_frame.pack_forget()
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.current_screen = "game"
        self._reset_game_view()
        self.log_event(
            f"Entered game table with a {len(self.selected_setup_cards)}-card deck."
        )

    def _reset_game_view(self):
        """Remove visual state left by a previous match before reconnecting."""
        self.status_bar.config(text="Turn: 0 | Phase: LOBBY | Active: - | Priority: -")
        self.opp_header_lbl.config(text="Opponent: [Waiting...] | Life: 20 | Hand: 0 | Library: 0 | GY: 0")
        self.local_header_lbl.config(text="You (Local): [Waiting...] | Life: 20 | Library: 0 | GY: 0")
        self.stack_listbox.delete(0, tk.END)
        for container in (self.opp_battlefield_frame, self.shared_battlefield_frame, self.hand_container):
            for widget in container.winfo_children():
                widget.destroy()
        self.log_text.config(state=tk.NORMAL)
        self.log_text.delete("1.0", tk.END)
        self.log_text.config(state=tk.DISABLED)

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
            self.log_event(
                f"State Update: Turn {st.get('turn')} | Phase: {st.get('phase')} "
                f"| Priority: {st.get('priority_holder')}"
            )
            if st.get("phase") == "MULLIGAN" and not st.get("mulligan_kept", False) and self._last_mulligan_prompt_seq != pdu.get("seq_num"):
                self._last_mulligan_prompt_seq = pdu.get("seq_num")
                self._show_mulligan_dialog({"cards_to_bottom_count": st.get("mulligans_taken", 0)})
            elif (
                st.get("phase") == "CLEANUP"
                and st.get("active_player") == self.client_state.player_id
                and len(self.client_state.get_local_hand()) > 7
                and self._last_discard_prompt_seq != pdu.get("seq_num")
            ):
                self._last_discard_prompt_seq = pdu.get("seq_num")
                self._show_discard_dialog({"count": len(self.client_state.get_local_hand()) - 7})
        elif ptype == "PHASE_TRANSITION":
            self.log_event(f"Phase -> {pdu.get('to_phase')} (Active: {pdu.get('active_player')})")
            if pdu.get("to_phase") == "ASSIGN_DAMAGE_ORDER" and pdu.get("active_player") == self.client_state.player_id:
                self._show_damage_order_dialog()
        elif ptype == "PRIORITY_GRANT":
            self.log_event(f"Priority -> {pdu.get('player_id')}")
        elif ptype == "STACK_PUSH":
            self.log_event(f"Stack Push: {pdu.get('source')} by {pdu.get('controller')}")
        elif ptype == "STACK_RESOLVE":
            self.log_event(f"Stack Resolve: {pdu.get('stack_item_id')} -> {pdu.get('result')}")
        elif ptype == "MULLIGAN_PROMPT":
            self._show_mulligan_dialog(pdu)
        elif ptype == "TRIGGER_ORDER":
            self._show_trigger_order_dialog(pdu)
        elif ptype == "TRIGGER_CHOICE":
            self._show_trigger_choice_dialog(pdu)
        elif ptype == "DISCARD_PROMPT":
            self._show_discard_dialog(pdu)
        elif ptype == "GAME_OVER":
            winner_id = pdu.get("winner_id") or pdu.get("winner", "UNKNOWN")
            reason = pdu.get("reason", "")
            self.log_event(f"GAME OVER: Winner {winner_id} ({reason})")
            messagebox.showinfo("Game Over", f"Game Over!\nWinner: {winner_id}\nReason: {reason}")
            self._return_to_lobby()
        elif ptype == "ERROR":
            self.log_event(f"ERROR [{pdu.get('code')}]: {pdu.get('message')}")
            messagebox.showerror(f"Error ({pdu.get('code')})", pdu.get('message', 'Illegal Action'))
            rejected_type = pdu.get("rejected_action", {}).get("type")
            st = self.client_state.current_state
            if rejected_type == "MULLIGAN_CHOICE" and st.get("phase") == "MULLIGAN":
                self._show_mulligan_dialog({"cards_to_bottom_count": st.get("mulligans_taken", 0)})
            elif rejected_type == "DISCARD" and st.get("phase") == "CLEANUP":
                self._show_discard_dialog({"count": max(1, len(self.client_state.get_local_hand()) - 7)})
            elif rejected_type == "TRIGGER_ORDER_RESPONSE" and self.client_state.pending_request:
                self._show_trigger_order_dialog(self.client_state.pending_request)
            elif rejected_type == "TRIGGER_CHOICE_RESPONSE" and self.client_state.pending_request:
                self._show_trigger_choice_dialog(self.client_state.pending_request)

        self.render_state()

    def _return_to_lobby(self):
        """Restore setup while retaining the protocol-required TCP connection."""
        self.client_state.reset_for_lobby()
        self.selected_card_id = None
        self.selected_permanent_id = None
        self.selected_attackers.clear()
        self.selected_blockers.clear()
        self.selected_block_target = None
        self._last_mulligan_prompt_seq = None
        self._last_discard_prompt_seq = None
        self._set_connection_status(
            "Match ended. Choose a deck and press Begin for a rematch.",
            error=False,
        )
        self._show_welcome_screen()

    def _show_mulligan_dialog(self, pdu: Dict[str, Any]):
        keep = messagebox.askyesno("Mulligan Choice", "Do you want to KEEP your opening hand? (No = Mulligan)")
        cards_to_bottom: List[str] = []
        if keep:
            cards_bottom_cnt = pdu.get("cards_to_bottom_count", 0)
            if cards_bottom_cnt > 0:
                cards_str = simpledialog.askstring("Cards to Bottom", f"Select {cards_bottom_cnt} card ID(s) to put on bottom of library (comma-separated):")
                cards_to_bottom = [c.strip() for c in cards_str.split(",")] if cards_str else []

        if self.send_action_fn:
            action = self.client_state.build_mulligan_choice(keep, cards_to_bottom)
            self.send_action_fn(action)
            self.log_event(f"Sent Mulligan Choice: Keep={keep}, Bottom={cards_to_bottom}")

    def _show_trigger_choice_dialog(self, pdu: Dict[str, Any]):
        trg_id = pdu.get("trigger_id", "")
        summary = pdu.get("effect_summary") or pdu.get("summary", "")
        accept = messagebox.askyesno("Triggered Ability", f"Trigger ({trg_id}):\n{summary}\nDo you accept?")
        chosen_target = None
        if accept and pdu.get("requires_target"):
            legal_targets = pdu.get("legal_targets", [])
            chosen_target = simpledialog.askstring("Select Target", f"Legal targets: {', '.join(legal_targets)}\nEnter target:")
        if self.send_action_fn:
            action = self.client_state.build_trigger_choice_response(trg_id, accept, chosen_target)
            self.send_action_fn(action)
            self.log_event(f"Sent Trigger Choice ({trg_id}): Accept={accept}, Target={chosen_target}")

    def _show_trigger_order_dialog(self, pdu: Dict[str, Any]):
        trg_ids = pdu.get("trigger_ids", [])
        order_str = simpledialog.askstring("Order Triggers", f"Specify trigger order (bottom to top, comma-separated):\nTriggers: {', '.join(trg_ids)}")
        ordered = [t.strip() for t in order_str.split(",")] if order_str else trg_ids
        if self.send_action_fn:
            action = self.client_state.build_trigger_order_response(ordered)
            self.send_action_fn(action)
            self.log_event(f"Sent Trigger Order Response: {ordered}")

    def _show_discard_dialog(self, pdu: Dict[str, Any]):
        count = pdu.get("count", 1)
        cards_str = simpledialog.askstring("Discard Required", f"Discard {count} card ID(s) (comma-separated):")
        to_discard = [c.strip() for c in cards_str.split(",")] if cards_str else []
        if self.send_action_fn:
            action = self.client_state.build_discard(to_discard)
            self.send_action_fn(action)
            self.log_event(f"Sent Discard: {to_discard}")

    def _show_damage_order_dialog(self):
        blockers = self.client_state.current_state.get("combat", {}).get("blockers", [])
        grouped: Dict[str, List[str]] = {}
        for declaration in blockers:
            grouped.setdefault(declaration.get("blocking_id", ""), []).append(declaration.get("creature_id", ""))
        for attacker_id, blocker_ids in grouped.items():
            if len(blocker_ids) < 2:
                continue
            entered = simpledialog.askstring(
                "Assign Damage Order",
                f"Order blockers for {attacker_id} from first to last (comma-separated):\n{', '.join(blocker_ids)}",
            )
            order = [card.strip() for card in entered.split(",")] if entered else blocker_ids
            if self.send_action_fn:
                self.send_action_fn(self.client_state.build_assign_damage_order(attacker_id, order))
                self.log_event(f"Sent damage order for {attacker_id}: {order}")

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
        hand_cards = self.client_state.get_local_hand()
        for card_id in hand_cards:
            self._create_hand_card(self.hand_container, card_id)

        self.stack_listbox.delete(0, tk.END)
        stk = st.get("stack", [])
        for idx, item in enumerate(stk):
            self.stack_listbox.insert(tk.END, f"[{idx}] {item.get('source')} ({item.get('item_type')}) -> {item.get('targets')}")

        has_priority = (st.get("priority_holder") == local_p)
        phase = st.get("phase", "")
        is_active_player = st.get("active_player") == local_p
        stack_is_empty = not stk
        is_main_phase = phase in ("PRECOMBAT_MAIN", "POSTCOMBAT_MAIN")
        has_sorcery_timing = has_priority and is_active_player and is_main_phase and stack_is_empty
        selected_definition = self.catalog.get_definition(self.selected_card_id) if self.selected_card_id else None

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
            can_play_selected_land = bool(
                selected_definition
                and selected_definition.is_land()
                and has_sorcery_timing
            )
            can_cast_selected_spell = bool(
                selected_definition
                and not selected_definition.is_land()
                and (selected_definition.is_instant() or has_sorcery_timing)
            )
            self.play_land_btn.config(state=tk.NORMAL if can_play_selected_land else tk.DISABLED)
            self.cast_spell_btn.config(state=tk.NORMAL if can_cast_selected_spell else tk.DISABLED)
            self.activate_ability_btn.config(state=tk.NORMAL)
            priority_hint = "YOUR PRIORITY"
            if not is_active_player:
                priority_hint += " — instants, abilities, or pass"
            self.action_status_lbl.config(text=priority_hint, foreground=self.ACCENT_GREEN)
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

        combat_attackers = {
            declaration.get("creature_id")
            for declaration in self.client_state.current_state.get("combat", {}).get("attackers", [])
        }
        combat_blockers = {
            declaration.get("creature_id")
            for declaration in self.client_state.current_state.get("combat", {}).get("blockers", [])
        }
        is_attacker = cid in self.selected_attackers or cid in combat_attackers
        is_blocker = any(declaration.get("creature_id") == cid for declaration in self.selected_blockers) or cid in combat_blockers
        is_selected = (self.selected_permanent_id == cid)
        bg_col = self.ACCENT_RED if is_attacker else (self.CARD_SELECTED_BG if is_selected else ("#2a2b3c" if not is_opponent else "#212230"))
        fg_col = "#000000" if is_attacker else self.TEXT_COLOR
        border_col = self.ACCENT_RED if tapped else self.ACCENT_BLUE

        perm_frame = tk.Frame(parent, bg=bg_col, bd=2, relief=tk.RAISED if is_selected else tk.GROOVE, padx=6, pady=4, cursor="hand2")
        perm_frame.pack(side=tk.LEFT, padx=4, pady=2)

        status_str = "[ATTACKING]" if is_attacker else ("[BLOCKING]" if is_blocker else ("[TAPPED]" if tapped else "[READY]"))
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
            elif st.get("phase") == "DECLARE_BLOCKERS":
                if is_opponent and cid in combat_attackers:
                    self.selected_block_target = cid
                    self.log_event(f"Selected attacker to block: {cid}")
                elif not is_opponent and self.selected_block_target:
                    self.selected_blockers = [
                        declaration for declaration in self.selected_blockers
                        if declaration.get("creature_id") != cid
                    ]
                    self.selected_blockers.append({"creature_id": cid, "blocking_id": self.selected_block_target})
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
        if def_obj.is_land():
            messagebox.showinfo("Play Land", "Lands cannot be cast as spells. Use Play Land during your own main phase.")
            return

        target_input = simpledialog.askstring("Targets", f"Target ID(s) for {def_obj.name} (comma-separated, leave blank if none):")
        targets = [t.strip() for t in target_input.split(",")] if target_input else []
        mana_payment = {
            ("X" if color == "Generic" else color): amount
            for color, amount in def_obj.mana_cost.items() if amount
        }

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
            base_id = self.catalog.extract_base_id(self.selected_permanent_id)
            generic_cost = {"millstone": 2, "rod_of_ruin": 3}.get(base_id, 0)
            cost_payment: Dict[str, Any] = {
                "tap": True,
                "mana": ({"X": generic_cost} if generic_cost else {}),
            }
            if base_id == "mother_of_runes":
                color = simpledialog.askstring("Protection Color", "Choose W, U, B, R, or G:")
                if not color or color.strip().upper() not in {"W", "U", "B", "R", "G"}:
                    messagebox.showinfo("Protection Color", "Enter one of W, U, B, R, or G.")
                    return
                cost_payment["color"] = color.strip().upper()
            pdu = self.client_state.build_activate_ability(
                self.selected_permanent_id, 0, targets,
                cost_payment,
            )
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
