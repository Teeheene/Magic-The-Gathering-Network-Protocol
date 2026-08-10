# Base-Runtime Task Progress

## Priority 0 (Base Runtime Core Correctness)
- [x] P0-1: FIX ACTIVATED ABILITY RESOLUTION (Authoritative ABILITY stack item resolution)
- [x] P0-2: FIX COUNTERSPELL ZONE MOVEMENT (Countered spell cards move to owner graveyard)
- [x] P0-3: FIX GRAVEDIGGER TRIGGER CHOICE PERSISTENCE (Retain targeted triggers in pending_triggers during choice)
- [x] P0-4: IMPLEMENT REAL TRIGGER_ORDER (Simultaneous trigger ordering with AP/NAP stack placement)
- [x] P0-5: FIX EVENT EMISSION FOR ACTIVATED ABILITIES (Emit became_target for activated ability targets)
- [x] P0-6: FIX SPELL / TRIGGER / PRIORITY PDU ORDERING (STACK_PUSH -> Events -> Triggers -> Single Priority Grant)
- [x] P0-7: FINISH REQUEST TOKEN USAGE (Strict correlation token validation across all handlers)
- [x] P0-8: ACTUALLY CENTRALIZE ERROR ROUTING (Centralized send_error with active request sequence numbers)
- [x] P0-9: FIX PRIORITY TIMEOUT RESULT (Priority expiration ends game with reason DISCONNECT, socket open)
- [x] P0-10: COMPLETE HEARTBEAT TESTING (Matching PONG, mismatched PONG, and timeout unit/integration tests)
- [x] P0-11: IMPLEMENT THE REAL SAME-SOCKET REMATCH TEST (TCP socket test Game 1 -> CONCEDE -> GAME_OVER -> LOBBY -> fresh PLAYER_READY -> Game 2)
- [x] P0-12: FIX LOBBY STATE SEMANTICS IF NEEDED (ready_count checks ready_in_lobby == True)
- [x] P0-13: BASE FIVE EFFECTS MUST BE PROVEN END TO END (E2E tests for Lightning Bolt, Flame Slash, Counterspell, Unsummon, Naturalize)
- [x] P0-14: TASK.MD MUST BE TRUTHFUL
- [x] P0-15: DO NOT EXPAND QT YET (GUI scope preserved)
- [x] P0-16: Real socket rematch test passes end-to-end
- [x] P0-17: Full current automated test suite passes

## Future / Pending Phases
- [ ] P2-6: 58-Card Bonus Set Implementation (Pending post-pass approval)
- [ ] P3-3: Major Qt GUI Feature Expansion (Pending post-pass approval)
