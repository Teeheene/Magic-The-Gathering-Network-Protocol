# MTGNP rubric evidence checklist

This is an evidence map, not a claim that a live demonstration has been performed. Run the listed
tests and demo actions before submission.

| Criterion | Production evidence | Proof test(s) | Demo action |
|---|---|---|---|
| Verbose TCP prerequisite | `app/server/connection.py`, shared protocol labels | `test_verbose_logging` | Start `python -m app.server -v`; connect two verbose clients |
| TCP accept / third refusal | server connection lifecycle | `test_two_client_handshake_rematch_and_3rd_connection_refusal` | Connect A, B, then a third client |
| Framing / UTF-8 / max payload | `app/shared/protocol.py` | protocol/client tests | Send normal and oversized framed PDUs |
| PDU structure / sequence | dispatcher and builders | `test_gameplay_action_builders_echo_seq_num`, runtime corrections | Inspect verbose PDU `seq_num` correlation |
| Lobby / PLAYER_READY | server lobby and Qt lobby | `test_player_ready_handshake`, Qt tests | Connect, select deck, press READY |
| GAME_SETUP / London mulligan | server mulligan flow and client dialog | base/integration tests | Select cards to bottom, mulligan, then keep |
| Phase transitions | authoritative game engine | `test_advance_phase_complete_turn_to_next_upkeep` | Pass priority through phases |
| GAME_OVER / restart | lifecycle reset | same-socket rematch test | Concede, press REMATCH on same sockets |
| Authoritative state / hidden info | personalized state updates | `test_opponent_hand_remains_hidden` | Compare each player's hand view |
| Priority / stack | stack and priority engine | production integration stack tests | Cast spell, respond, pass twice, inspect LIFO |
| Combat | attacker/blocker/order/damage engine | combat and first/double-strike tests | Declare attackers, blockers, damage order |
| Client send/render | CLI and `app/client/qt` | `tests/test_client*.py`, `tests/test_qt*.py` | Perform land, spell, target, combat actions |
| PING/PONG | connection heartbeat | heartbeat tests | Observe verbose PING/PONG |
| ERROR handling | dispatcher error path | client error and stale-action tests | Send stale/illegal action; continue play |
| Code quality | modular app/client, app/server, app/shared | full suite + compileall | Review README/runbook and clean status |
| Full card-effects bonus | `CARD_SUPPORT_MATRIX.md` | card-effect/protocol tests | Use CLI flows for complex cards |
| GUI bonus | PySide6 MainWindow/CardWidget/ZoneWidget | Qt and asset tests | Connect, mulligan, render board, cast/pass/concede |

Card matrix target is 50 COMPLETE, 0 PARTIAL, 0 MISSING, 8 NO SPECIAL ENGINE WORK REQUIRED.
Experimental `CARD_CHOICE_*`, `SUSPEND_CARD`, and `CAST_SPELL.mode` are documented extensions.
