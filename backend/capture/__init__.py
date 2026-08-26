"""`capture` — syntax-driven thought capture. This is the app.

It began as a sibling package to a tech tree that shared this process. The tree
was removed on 2026-08-27, and the package boundary stayed, because it now
draws a line worth having rather than the one it was drawn for: `app/` is the
machine — the data directory, the blob store, the backup, the process — and
everything in here is about what the user wrote. `app/` knows nothing about
what a capture is, and that is what kept the removal a deletion rather than an
untangling. Its log lives under `data/capture/`.

Ported from a Next.js/Prisma/Postgres source. `trophic/` holds the reference
bundle and, more importantly, the golden corpus that defines correct behaviour;
every module in here should be verifiable against it.
"""
