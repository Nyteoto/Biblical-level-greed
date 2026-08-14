"""`capture` — syntax-driven thought capture, a sibling app to the tech tree.

Kept in its own package rather than folded into `app/` because it shares this
repo's *shape* (append-only log, disposable SQLite projection, no auth, one
user) and nothing else: its events, its fold and its board have no vocabulary
in common with the practice tree. It gets its own log under `data/capture/`.

Ported from a Next.js/Prisma/Postgres source. `trophic/` holds the reference
bundle and, more importantly, the golden corpus that defines correct behaviour;
every module in here should be verifiable against it.
"""
