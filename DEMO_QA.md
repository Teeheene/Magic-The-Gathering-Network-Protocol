# Demo QA quick answers

- **Why TCP?** Reliable ordered bytes; MTGNP adds its own four-byte length framing.
- **Why framing?** A big-endian unsigned length precedes UTF-8 JSON; `recv()` may return partial data.
- **How do tokens work?** Request-specific `seq_num` values correlate actions; phase and priority tokens are distinct.
- **Who is authoritative?** The server validates rules, state, targets, priority, and hidden information.
- **How is the stack resolved?** Responses are pushed, then two consecutive passes resolve the top item (LIFO).
- **How does combat work?** The server controls declaration, legality, assignment, damage, SBA, and phase transitions.
- **How does heartbeat work?** Client PING receives matching PONG; timeout marks the connection unhealthy.
- **How are stale actions rejected?** The server compares the supplied request token and emits `STALE_ACTION`.
- **How does rematch work?** GAME_OVER resets the match while retaining both sockets; fresh READY starts a new game.
- **Why do PONG/ERROR matter to CONCEDE?** CONCEDE echoes the literal latest received server PDU sequence.
- **What are card-choice extensions?** `CARD_CHOICE_REQUEST/RESPONSE` model private ordering, modes, and payments.
- **Why Suspend needs an extension?** Delayed Rift Bolt choices need an explicit client/server interaction outside base PDUs.
- **Why are images optional?** Asset requests are asynchronous and cached; metadata cards remain playable offline.
- **How was AI used?** Codex/ChatGPT assisted implementation and tests; all changes were verified with pytest and compileall.
