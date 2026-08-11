# MTGNP demo runbook

Use four terminals from the repository root.

1. `python -m app.server -v --port 4444`
2. `python -m app.client -v --player-id alice --host 127.0.0.1 --port 4444`
3. `python -m app.client -v --player-id bob --host 127.0.0.1 --port 4444`
4. Optional GUI: `python -m app.client --qt --player-id demo --host 127.0.0.1 --port 4444`

Safest sequence: connect both clients, submit READY, mulligan/keep, play a land, cast a spell,
respond and pass twice, advance to combat, declare attackers/blockers, then concede. Repeat READY
on the same sockets to show rematch. Keep verbose logs visible: every complete sent/received PDU
must have an unmistakable direction label. If web artwork is unavailable, continue with metadata
cards; imagery is presentation-only.
