# MTGNP 1.0 — Magic: The Gathering Network Protocol

An authoritative client-server implementation of the official **MTGNP 1.0** specification (`CSNETWK_MP_MTGNP.md`), built in Python with support for CLI and PySide6 graphical desktop clients.

---

## 🚀 Features

- **Authoritative Server Engine**: Multi-threaded TCP server handling lobby management, session restarts, active 3rd connection refusal, and London Mulligan handshakes.
- **Strict Protocol Correlation**: 4-byte big-endian framing (`MAX_PAYLOAD_SIZE = 65535`), `seq_num` echo correlation for `PONG`, `ERROR`, and `PRIORITY_GRANT` tokens.
- **Verbose Server Mode**: Launch with `--verbose` or `-v` to print formatted `[SERVER SENT PDU]` and `[SERVER RECEIVED PDU]` logs for grading compliance.
- **58 Fixed Card Set**: Reconciled master catalog (`mtgnp_master_card_list.csv`), instance ID deck validation, and rule enforcement (e.g. Defender, Flying, Vigilance, First/Double Strike, no trample overflow per MTGNP 1.0 §7).
- **Modular Domain Architecture**:
  - `app/server/engine/triggers.py`: Event bus & triggered ability engine (`TRIGGER_ORDER`, `TRIGGER_CHOICE`).
  - `app/server/engine/sba.py`: State-Based Actions loop (lethal damage, 0 life AP/NAP loss, deckout).
  - `app/server/engine/effects.py`: Full spell resolution handlers (Ponder, Mana Leak, Dark Ritual, Giant Growth, etc.).
- **PySide6 Graphical Desktop Client**: Interactive GUI under `app/client/qt/` with battlefield zone layouts, hand controls, stack views, and prompt dialogs.

---

## 🛠️ Requirements & Setup

- **Python**: 3.10+
- **Dependencies**: `PySide6`, `pytest`

```bash
pip install PySide6 pytest
```

---

## 🎮 Running the Application

### 1. Start the Server (Verbose Mode)

```bash
python -m app.server --verbose --port 4444
```

### 2. Start the CLI Client

```bash
python -m app.client --player-id alice --server-host 127.0.0.1 --server-port 4444
```

### 3. Start the PySide6 Graphical Client

```bash
python -m app.client.qt --player-id bob --server-host 127.0.0.1 --server-port 4444
```

---

## 🧪 Running the Test Suite

Execute the entire test suite across unit, domain engine, GUI, and real-socket integration tests:

```bash
python -m pytest tests/ -v
```

The Qt client is an off-screen-testable PySide6 desktop client. It provides connection and
lobby/deck selection, London mulligan, battlefield/hand/stack/exile views, priority, casting,
targets, mana and kicker prompts, activated abilities, combat assignment, trigger/card-choice
dialogs, suspend, concede, game-over, and same-socket rematch. The server remains authoritative;
the experimental `CARD_CHOICE_REQUEST`/`CARD_CHOICE_RESPONSE` and `SUSPEND_CARD` PDUs are
documented in `CSNETWK_MP_MTGNP.md` and handled by both CLI and Qt clients.

For headless CI use:

```bash
QT_QPA_PLATFORM=offscreen python -m pytest tests/ -v --tb=short
```

### Card artwork cache

Artwork is fetched asynchronously from Scryfall and cached under the platform user cache
(`QStandardPaths.CacheLocation/MTGNP/cards`). Internet access is optional after caching; failed
requests retain fully playable metadata-only cards. The optional developer utility
`python -m app.client.qt.precache_assets` warms one request per unique base card. Artwork is
presentation-only and remains owned by its provider.
