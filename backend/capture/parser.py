"""Capture's syntax parser: raw line in, metadata out.

Extracts from raw text:
 - folders:    <pointer>        e.g. <career>, <the backup-system>
 - times:      {time-link}      e.g. {q3}, {review_monday}
 - patterns:   \\sentiment       e.g. \\hate, \\burnout, \\win
 - places:     @place           e.g. @helsinki, @the-office
 - counts:     #42              e.g. #100, #3
 - directives: --foldername     direct-file into a folder (stripped from text)
 - todos:      --todo           that line becomes a checkbox

Rules: captures are trimmed, lowercased and de-duplicated, keeping
first-appearance order; empty captures are dropped; `\\ ` is a literal
backslash rather than a sentiment; `@` opens a place only at the start of a
word, because `a@b.com` is an address; and text inside "quotes" triggers
nothing.

`places` is this port's own addition and has no fixtures behind it — the
corpus adapter projects six named fields and does not see it, so the 1185
cases still pin every one of the source's. What the corpus *does* pin is the
boundary rule: forty of its inputs carry `a@b.com`, and all forty expect no
capture. A place is deliberately the same shape as a pattern and points at
nothing; only `<folder>` resolves anywhere. It is a separate list rather than
a second class of pattern so that asking "where have I been" is a query.

`counts` is the same kind of addition, one sigil later: a bare number you
attach to a line — a tempo, a rep count, a take — without it polluting
`patterns` the way typing `\tempo100` used to. It reuses `places`' word-start
guard rather than inventing one: `F#7`, a sharp chord, has `#` preceded by a
letter and is correctly read as plain text, while `did it #5 times` has `#`
preceded by a space and captures. No corpus fixture exercises `#` at all, so
there is nothing here for the golden corpus to pin either way.

Why it is shaped this way
-------------------------
This is a line-by-line port of `trophic/reference/logic/parser.ts`, and it is
deliberately *not* idiomatic where idiom would change behaviour. The output is
pinned by 1185 golden fixtures generated from the original TypeScript, so the
JavaScript's quirks are the specification, not accidents to clean up:

 - **The regex classes are hand-scanned, not compiled.** The source uses
   `\\p{L}\\p{N}\\p{M}` under `/u`; Python's `re` has no `\\p{...}`, and `\\w` is
   the wrong shape — it includes `_` and excludes combining marks, so Yoruba
   `\\rẹ̀wà` (fixture `parse-1179`) would lose its tone marks. `_scan_patterns`
   and `_scan_directives` walk the string against `unicodedata.category`
   instead, reproducing the regexes' greediness and their restart-at-+1 on a
   failed match.
 - **Word boundaries are ASCII.** JavaScript's `\\b` is defined over
   `[A-Za-z0-9_]` even under `/u`; Python's is Unicode-aware. `--todoé` matches
   `/--todo\\b/` in JS and would not here, so the boundary is checked by hand.
 - **Whitespace is JavaScript's.** `trim()` and `\\s` cover `\\uFEFF` (which
   Python does not consider whitespace) and exclude `\\x1c`–`\\x1f` (which
   Python strips). `js_trim` spells the set out.
 - **A whitespace-only quoted directive yields `""`, not `None`.** The source
   assigns the empty name, breaks, and then re-tests it for falsiness — so the
   unquoted scan still runs, and if it finds nothing the returned directive is
   the empty string. Preserved on purpose.

Nothing here reads or writes: it is a pure function, which is what lets the
parsed fields live in the SQLite index and be recomputed by replaying the log.
The log stores only `raw_text`; folders, times and patterns are a projection of
it, so retuning this file re-derives all of history for free.
"""

from __future__ import annotations

import re
import string
import unicodedata
from dataclasses import dataclass, field

# ── The syntax ────────────────────────────────────────────────────────────

_FOLDER_RE = re.compile(r"<([^<>]+)>")
_TIME_RE = re.compile(r"\{([^{}]+)\}")
_QUOTED_RE = re.compile(r'"[^"]*"')
_ESCAPED_BACKSLASH_RE = re.compile(r"\\ ")
_DIRECTIVE_QUOTED_RE = re.compile(r'--"([^"]+)"')

# CLI navigation commands — full-line commands, not inline directives.
NAV_COMMANDS = frozenset(
    {"codex", "folders", "settings", "assign", "logout", "dev", "reply"}
)
# Two more names a directive may never take: `--draw` opens the sketch pad and
# `--todo` is handled per-line below.
_RESERVED = NAV_COMMANDS | {"draw", "todo"}

# ── JavaScript primitives Python spells differently ───────────────────────

# ECMAScript WhiteSpace + LineTerminator: what `trim()` strips and `\s` matches.
# Spelled out because neither `str.strip()` nor Python's `\s` is this set:
# JS strips U+FEFF and does not strip U+001C-001F; Python is the other way.
_JS_WS = frozenset(
    "\t\n\v\f\r \u00a0\u1680\u2028\u2029\u202f\u205f\u3000\ufeff"
    + "".join(chr(c) for c in range(0x2000, 0x200B))
)
_ASCII_WORD = frozenset(string.ascii_letters + string.digits + "_")


def js_trim(s: str) -> str:
    return s.strip("".join(_JS_WS))


def _is_ln(ch: str) -> bool:
    """`[\\p{L}\\p{N}]` — a letter or a number in any script."""
    return unicodedata.category(ch)[0] in ("L", "N")


def _is_lnm(ch: str) -> bool:
    """`[\\p{L}\\p{N}\\p{M}]` — the above, plus combining marks."""
    return unicodedata.category(ch)[0] in ("L", "N", "M")


def _has_boundary_at(text: str, end: int, last_matched: str) -> bool:
    """Is there a JavaScript `\\b` at `end`, having just matched `last_matched`?

    ASCII-only by definition of ECMAScript's `\\w`, which is why this cannot be
    Python's `\\b`: after `--café`, JS sees a non-word char and so requires the
    *next* char to be a word char for the boundary to exist.
    """
    before = last_matched[-1] in _ASCII_WORD
    after = end < len(text) and text[end] in _ASCII_WORD
    return before != after


# ── Capture collection ────────────────────────────────────────────────────


def _dedupe(names: list[str]) -> list[str]:
    """Trim, lowercase, drop the empties, keep first appearance order."""
    out: dict[str, None] = {}
    for name in names:
        captured = js_trim(name).lower()
        if captured:
            out[captured] = None
    return list(out)


def normalize_tag(raw: str) -> str:
    """Trim and lowercase a tag the way a captured `<tag>` is.

    Exported because tags arrive from two directions — typed inside a capture,
    and typed into the mapping screen — and a tag that normalises differently
    depending on which door it came through is two tags that look like one.
    """
    return js_trim(raw).lower()


def _collect(raw: str, pattern: re.Pattern[str]) -> list[str]:
    return _dedupe([m.group(1) for m in pattern.finditer(raw)])


def _scan_patterns(text: str) -> list[str]:
    """`/\\\\([\\p{L}\\p{N}\\p{M}]+(?:-[\\p{L}\\p{N}\\p{M}]+)*)/gu`, by hand.

    Hyphens are internal only: `\\a-` captures `a` and leaves the hyphen.
    """
    out: list[str] = []
    i, n = 0, len(text)
    while i < n:
        if text[i] != "\\" or i + 1 >= n or not _is_lnm(text[i + 1]):
            i += 1
            continue
        j = i + 1
        while j < n and _is_lnm(text[j]):
            j += 1
        while j + 1 < n and text[j] == "-" and _is_lnm(text[j + 1]):
            j += 1
            while j < n and _is_lnm(text[j]):
                j += 1
        out.append(text[i + 1 : j])
        i = j  # resume after the match, as /g does
    return out


def _scan_places(masked: str, raw: str) -> list[str]:
    """`/@([\\p{L}\\p{N}\\p{M}]+(?:-[\\p{L}\\p{N}\\p{M}]+)*)/gu`, by hand, plus a guard.

    The body is `_scan_patterns`' exactly, because a place and a pattern are the
    same shape of word. The difference is the guard: `@` opens a place only at
    the start of a word. `\\` is punctuation nobody types inside a word; `@` is
    an email address, and forty fixtures say so.

    The boundary is read from `raw`, not from `masked`. Masking preserves
    length, so the indices agree — but what it does not preserve is which
    character sits *before* a match, and `"quoted"@x` must not become a place
    merely because the quote was blanked to spaces.
    """
    out: list[str] = []
    i, n = 0, len(masked)
    while i < n:
        if masked[i] != "@" or i + 1 >= n or not _is_lnm(masked[i + 1]):
            i += 1
            continue
        if i > 0 and raw[i - 1] not in _JS_WS:
            i += 1
            continue
        j = i + 1
        while j < n and _is_lnm(masked[j]):
            j += 1
        while j + 1 < n and masked[j] == "-" and _is_lnm(masked[j + 1]):
            j += 1
            while j < n and _is_lnm(masked[j]):
                j += 1
        out.append(masked[i + 1 : j])
        i = j  # resume after the match, as /g does
    return out


def _scan_counts(masked: str, raw: str) -> list[str]:
    """`#` followed by digits, word-start only — `places`' guard, one sigil
    later.

    The body is plain digits rather than `_is_lnm`: a count is a number, not a
    word. The guard is `_scan_places`' exactly, read off `raw` for the same
    reason — masking must not manufacture a word start where the unmasked text
    has none. That guard is what keeps a sharp chord (`F#7`, `#` preceded by a
    letter) from reading as a count while `did it #5 times` (`#` preceded by a
    space) still does.
    """
    out: list[str] = []
    i, n = 0, len(masked)
    while i < n:
        if masked[i] != "#" or i + 1 >= n or not masked[i + 1].isdigit():
            i += 1
            continue
        if i > 0 and raw[i - 1] not in _JS_WS:
            i += 1
            continue
        j = i + 1
        while j < n and masked[j].isdigit():
            j += 1
        out.append(masked[i + 1 : j])
        i = j  # resume after the match, as /g does
    return out


def _scan_directives(text: str):
    """`/--([\\p{L}\\p{N}][\\p{L}\\p{N}\\p{M}_-]*)/gu`, by hand.

    The tail class contains `-`, so the match is greedier than it looks:
    `--todo--x` is one directive named `todo--x`, not `todo`.
    """
    i, n = 0, len(text)
    while i + 2 < n:
        if text[i] != "-" or text[i + 1] != "-" or not _is_ln(text[i + 2]):
            i += 1
            continue
        j = i + 3
        while j < n and (_is_lnm(text[j]) or text[j] in "_-"):
            j += 1
        yield text[i + 2 : j]
        i = j


# ── Masking ───────────────────────────────────────────────────────────────


def _mask_quoted(text: str) -> str:
    """Blank out quoted strings so their contents don't trigger sentiments."""
    return _QUOTED_RE.sub(lambda m: " " * len(m.group()), text)


def _mask_escaped_backslash(text: str) -> str:
    """Blank out `\\ `, which is a literal backslash rather than a pattern."""
    return _ESCAPED_BACKSLASH_RE.sub("  ", text)


# ── Stripping (the `cleanText` half) ──────────────────────────────────────


def _strip(
    line: str, needle: str, *, boundary: bool = True, eat_leading_ws: bool = False
) -> str:
    """Remove every case-insensitive `needle` from `line`.

    `boundary` requires a JavaScript `\\b` after the match, which the two
    unquoted forms (`--todo\\b`, `--directive\\b`) carry and the quoted form
    (`--"directive"`) does not. `eat_leading_ws` adds the `\\s*` in front of
    `/\\s*--todo\\b/gi`. Matches are found left to right and never overlap, so
    the whitespace a match swallows is only what the previous one left behind.
    """
    pattern = re.compile(re.escape(needle), re.IGNORECASE)
    out: list[str] = []
    pos = 0  # everything before this has been emitted or consumed
    search_from = 0
    while True:
        m = pattern.search(line, search_from)
        if m is None:
            break
        if boundary and not _has_boundary_at(line, m.end(), m.group()):
            search_from = m.start() + 1
            continue
        start = m.start()
        if eat_leading_ws:
            while start > pos and line[start - 1] in _JS_WS:
                start -= 1
        out.append(line[pos:start])
        pos = search_from = m.end()
    out.append(line[pos:])
    return "".join(out)


def _has_todo(line: str) -> bool:
    return _strip(line, "--todo") != line


# ── The parse ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ParsedEntry:
    """Everything derivable from one raw capture. Stored in the index, never
    in the log — see the module docstring."""

    folders: list[str] = field(default_factory=list)
    times: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    places: list[str] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)
    directive: str | None = None  # --foldername directive (lowercased)
    todo_lines: list[int] = field(default_factory=list)  # 0-based line indices
    clean_text: str = ""  # raw_text with --foldername and --todo stripped


def parse_entry(raw: str) -> ParsedEntry:
    masked = _mask_escaped_backslash(_mask_quoted(raw))

    folders = _collect(masked, _FOLDER_RE)
    times = _collect(masked, _TIME_RE)
    patterns = _dedupe(_scan_patterns(masked))
    places = _dedupe(_scan_places(masked, raw))
    counts = [int(c) for c in _dedupe(_scan_counts(masked, raw))]

    # Find --"quoted folder" or --foldername (quoted form takes priority). The
    # quoted form has to match on `raw`: masking blanked its contents out.
    directive: str | None = None
    for m in _DIRECTIVE_QUOTED_RE.finditer(raw):
        name = js_trim(m.group(1)).lower()
        if name in _RESERVED:
            continue
        directive = name
        break
    if not directive:  # None *or* "" — see the module docstring
        for candidate in _scan_directives(masked):
            name = candidate.lower()
            if name in _RESERVED:
                continue
            directive = name
            break

    lines = raw.split("\n")
    todo_lines: list[int] = []
    clean_lines: list[str] = []

    for i, line in enumerate(lines):
        if _has_todo(line):
            todo_lines.append(i)
            line = js_trim(_strip(line, "--todo", eat_leading_ws=True))
        if directive:
            line = js_trim(_strip(line, f'--"{directive}"', boundary=False))
            line = js_trim(_strip(line, f"--{directive}"))
        clean_lines.append(line)

    clean_text = js_trim(re.sub(r"\n{3,}", "\n\n", "\n".join(clean_lines)))

    return ParsedEntry(
        folders=folders,
        times=times,
        patterns=patterns,
        places=places,
        counts=counts,
        directive=directive,
        todo_lines=todo_lines,
        clean_text=clean_text,
    )
