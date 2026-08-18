"""Paths and tunables for capture. Everything else imports locations from here.

Reads `PGS_DATA_DIR` — the same variable the tech tree reads — and then claims
its own subtree under it. That is the whole of the "sibling app" arrangement:
one data root on one disk, backed up by one `backup.sh`, but two independent
logs that never have to agree about anything. Tests get isolation for free,
because `conftest.py` sets that variable before either app is imported.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

# Repo root is two levels up from backend/capture/.
ROOT = Path(__file__).resolve().parents[2]

DATA_DIR = Path(os.environ.get("PGS_DATA_DIR", ROOT / "data"))
CAPTURE_DIR = DATA_DIR / "capture"
LOG_DIR = CAPTURE_DIR / "log"
INDEX_PATH = Path(
    os.environ.get("PGS_CAPTURE_INDEX_PATH", CAPTURE_DIR / "index.sqlite")
)

# The source app caps a capture at 2000 characters. Kept, not because storage
# is short here, but because the capture bar is for a thought you can hold in
# your head — anything longer is a note, and notes have their own home.
MAX_RAW_LEN = 2000

# The source's folder-name cap, kept for the same reason it exists there: a
# folder name is read at a glance in a list, and one that wraps is not.
MAX_NAME_LEN = 60

# A shelf group's name. Shorter than a folder's, because it is drawn as a
# heading over a row of cards rather than inside one, and a heading that wraps
# costs more room than the cards it is labelling.
GROUP_NAME_MAX = 32

# A year, as the shelf and the group events spell it. Here rather than in
# `api.py` because `store.py` validates it too, and the request layer is not
# allowed to be the only thing that knows the shape of a stored field.
YEAR_RE = re.compile(r"^\d{4}$")

# How many `--todo` lines may stand unchecked at once, across the whole log.
#
# A cap rather than a setting, and a small one. An open todo is a promise to
# yourself, and a list that can grow without bound stops being a list of things
# you are going to do and becomes a list of things you feel bad about. Ten is
# the number of things a person will actually look at.
#
# It is enforced on the write, not drawn as a warning: a capture that would
# cross it is refused whole, including one entry carrying eleven todos at once.
# A limit you can exceed by typing faster is not a limit.
MAX_OPEN_TODOS = 10

# Where a folder is in its life. The empty one is the default and means "no
# lifecycle" — an interest you keep rather than a project you finish. Kept
# small on purpose: a longer list is a taxonomy, and a taxonomy is something
# you have to maintain before you are allowed to write anything down.
FOLDER_STATES = ("", "active", "shipped")

# Which way round `{03/04/26}` reads: "us" is March 4th, "row" is April 3rd.
# There is no settings UI for this and there should not be — it is a property
# of the person, not of a session, and it is wanted before the first reminder
# is ever typed. A env var, defaulting to the reading most of the world uses.
DATE_LOCALE = os.environ.get("PGS_CAPTURE_DATE_LOCALE", "row")


def ensure_dirs() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
