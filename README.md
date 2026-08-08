# MTGNP 1.0

A two-player, server-authoritative implementation of the Magic: The Gathering Multiplayer Network Protocol described by RFC 0001 (April 2026).

## Run

From the repository root, start the server:

```powershell
python -m app.server
```

Then start two graphical clients:

```powershell
python -m app.client
```

The GUI asks for the host, port, unique player ID, and a 1-50 card deck. The default port is `4444`. After a game ends, both clients return to the lobby and can send new `PLAYER_READY` messages over the same TCP connections.

## Architecture

- `app/server/network/server.py` owns the two persistent TCP seats and lobby lifecycle.
- `app/server/game/session.py` owns authoritative game state, mulligans, turn progression, priority, combat, and game-over detection.
- `app/server/game/` contains the stack, card effects, mana, combat, triggers, and state-based actions.
- `app/client/application.py` coordinates the GUI, transport, state, listener, and heartbeat.
- `app/client/gui.py` renders only server-provided visible state and creates action PDUs.
- `app/shared/card_catalog.json` is the out-of-band card catalog shared by clients and the server.

All network messages use a 4-byte big-endian length followed by UTF-8 JSON, with a maximum payload of 65,535 bytes.

## Test

```powershell
python -m unittest discover -v
```

GUI tests automatically skip when the environment has no Tk display.
