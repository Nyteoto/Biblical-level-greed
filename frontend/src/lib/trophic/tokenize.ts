// Span-level tokenizer for the capture bar's live syntax colouring and its
// autocomplete triggers.
//
// Copied verbatim from `trophic/reference/logic/tokenize.ts`, which is the
// exact source the golden corpus was generated from — for a TypeScript target
// the faithful port is the file itself, and any rewrite could only lose
// fidelity. Two things it must keep: offsets are UTF-16 code units (which is
// what a `<textarea>`'s selectionStart speaks), and `\p{…}` under `/u` is why
// `\rẹ̀wà` tokenizes whole. Do not "modernise" either.
//
// The backend does not have this; it only needs the parser. If a Python port
// is ever wanted, `verify_golden.py tokenize` has 395 cases waiting.
//
// **Two kinds are this port's own: `place` and `count`.** Everything above
// still holds for the other five — they are the source's, and the corpus is
// their spec — but `@helsinki` and `#42` do not exist upstream. They are
// added here rather than left for a rewrite because the corpus can still
// police it: no fixture contains a word-start `@` or `#`, so all 395 pass
// unchanged, and the seventeen that carry `a@b.com` are exactly what pins the
// boundary rule below — `count` reuses that same rule rather than a second
// one, which is also what keeps a sharp chord (`F#7`) from misreading as a
// count. New kinds are the cheap half; keeping the old five byte-identical is
// the half that matters.

export type TokenKind = "folder" | "time" | "pattern" | "place" | "count" | "directive" | "todo" | "text"

export type Token = {
  kind: TokenKind
  start: number
  end: number
  raw: string
  value: string // inner content, lowercased (empty for "text")
}

// Navigation commands that are full-line, not inline directives: the word
// after `--`, and the screen it opens.
//
// **The destination is here, beside the word, on purpose.** This used to be a
// bare Set, and the capture bar kept its own `if (cmd === '--folders' || …)`
// ladder saying where each one went. Two lists of the same vocabulary, and
// they had drifted: `--log` was in the ladder and not in the set, so the
// tokenizer read it as a directive and `validation.ts` painted it as a folder
// that does not exist — a refusal, in red, under a word that works. `--draw`
// had drifted the other way and was recognised by nobody who could act on it.
//
// `null` is a word this port knows and has no screen for. It still has to be
// in here: a command the tokenizer does not recognise becomes a `--directive`,
// and a directive naming no folder is a refusal.
export const NAV_COMMANDS: ReadonlyMap<string, string | null> = new Map([
  ["folders", "/log"],
  // Keeps the source's name even though the screen it opens is called the
  // log here — it is the same screen, under both words.
  ["log", "/log"],
  // The mapping screen is gone: pointing a tag at a folder is a fact about
  // the folder, so it happens on the folder's own lens. Same word, same act,
  // one screen fewer.
  ["assign", "/record"],
  ["settings", "/settings"],
  ["codex", null],
  ["logout", null],
  ["dev", null],
  // `--draw -Foldername` is a real command with an argument and is handled in
  // `validation.ts`; bare `--draw` is the sketch pad this port does not have.
  ["draw", null],
])

const PATTERNS: { kind: Exclude<TokenKind, "text">; re: RegExp; group?: number; filter?: (value: string) => boolean }[] = [
  { kind: "folder", re: /<([^<>]+)>/g },
  { kind: "time", re: /\{([^{}]+)\}/g },
  // Unicode-aware: accept letters + numbers + combining marks in any script.
  { kind: "pattern", re: /\\([\p{L}\p{N}\p{M}]+(?:-[\p{L}\p{N}\p{M}]+)*)/gu },
  // A place. Deliberately the same body as `pattern` — same scripts, same
  // hyphenation — because it is the same *kind* of thing: a bare word you tag a
  // line with, that points at nothing. Only `<folder>` resolves to anywhere.
  // It is its own kind rather than a second pattern so that "every place I have
  // written" is a query and not a convention, which is the whole reason for
  // spending a sigil on it.
  { kind: "place", re: /@([\p{L}\p{N}\p{M}]+(?:-[\p{L}\p{N}\p{M}]+)*)/gu },
  // A count. Same word-start guard as `place`, digits only: a number
  // attached to the line rather than a word. `F#7` (a sharp chord) has `#`
  // preceded by a letter and is correctly left as plain text.
  { kind: "count", re: /#(\d+)/g },
  // Quoted directive must come before unquoted so it wins on overlap
  {
    kind: "directive",
    re: /--"([^"]+)"/g,
    filter: (v) => !NAV_COMMANDS.has(v) && v !== "todo",
  },
  {
    kind: "directive",
    re: /--([\p{L}\p{N}][\p{L}\p{N}\p{M}_-]*)/gu,
    filter: (v) => !NAV_COMMANDS.has(v) && v !== "todo",
  },
  { kind: "todo", re: /--todo\b/gi },
]

/** Find ranges of quoted strings to suppress pattern matching inside them */
function quotedRanges(text: string): [number, number][] {
  const ranges: [number, number][] = []
  const re = /"[^"]*"/g
  for (const m of text.matchAll(re)) {
    ranges.push([m.index!, m.index! + m[0].length])
  }
  return ranges
}

function inQuoted(pos: number, ranges: [number, number][]): boolean {
  return ranges.some(([s, e]) => pos >= s && pos < e)
}

/** Check if a backslash at `pos` is escaped (followed by space) */
function isEscapedBackslash(text: string, pos: number): boolean {
  return text[pos] === "\\" && text[pos + 1] === " "
}

/**
 * `@` only opens a place, and `#` only opens a count, at the start of a word.
 *
 * This is the one rule `pattern` does not need and `place` cannot do without:
 * `\` is punctuation nobody types mid-word, but `@` is an email address. The
 * corpus is unambiguous about it — seventeen tokenize fixtures and forty parser
 * ones carry `a@b.com`, and every one expects plain text straight through.
 * `count` reuses the same guard for the same reason: `#` mid-word is a sharp
 * chord (`F#7`), not a number worth capturing.
 */
function atWordStart(text: string, pos: number): boolean {
  return pos === 0 || /\s/.test(text[pos - 1]!)
}

export function tokenize(text: string): Token[] {
  const quoted = quotedRanges(text)
  const matches: Token[] = []

  for (const { kind, re, filter } of PATTERNS) {
    for (const m of text.matchAll(re)) {
      // Skip patterns inside quoted strings. Places and counts too: "text
      // inside quotes triggers nothing" is the rule for the whole syntax, and
      // neither is the exception to it.
      if ((kind === "pattern" || kind === "place" || kind === "count") && inQuoted(m.index!, quoted)) continue
      // Skip escaped backslash (`\ `)
      if (kind === "pattern" && isEscapedBackslash(text, m.index!)) continue
      // An `@` inside a word is an address, not a place; a `#` inside a word
      // is a sharp chord, not a count. Same guard, same reason.
      if ((kind === "place" || kind === "count") && !atWordStart(text, m.index!)) continue

      const inner = kind === "todo" ? "todo" : (m[1]?.trim().toLowerCase() ?? "")
      if (!inner) continue
      if (filter && !filter(inner)) continue

      matches.push({
        kind,
        start: m.index!,
        end: m.index! + m[0].length,
        raw: m[0],
        value: inner,
      })
    }
  }
  matches.sort((a, b) => a.start - b.start)

  const tokens: Token[] = []
  let cursor = 0
  for (const t of matches) {
    if (t.start < cursor) continue // skip overlaps
    if (t.start > cursor) {
      tokens.push({
        kind: "text",
        start: cursor,
        end: t.start,
        raw: text.slice(cursor, t.start),
        value: "",
      })
    }
    tokens.push(t)
    cursor = t.end
  }
  if (cursor < text.length) {
    tokens.push({
      kind: "text",
      start: cursor,
      end: text.length,
      raw: text.slice(cursor),
      value: "",
    })
  }
  return tokens
}

// Find an open trigger immediately before `caret` — used by autocomplete.
export type ActiveTrigger = {
  char: "<" | "{" | "\\" | "-"
  start: number
  query: string
}

export function activeTrigger(text: string, caret: number): ActiveTrigger | null {
  const beforeCaret = text.slice(0, caret)

  // Check for --"quoted" directive trigger (user typing inside quotes)
  const quotedDashMatch = beforeCaret.match(/--"([^"]*)$/)
  if (quotedDashMatch) {
    const query = quotedDashMatch[1]!.toLowerCase()
    return { char: "-", start: quotedDashMatch.index!, query }
  }

  // Check for -- directive trigger (unquoted --foldername autocomplete)
  const dashMatch = beforeCaret.match(/--([\p{L}\p{N}][\p{L}\p{N}\p{M}_-]*)$/u)
  if (dashMatch) {
    const name = dashMatch[1]!.toLowerCase()
    if (!NAV_COMMANDS.has(name) && name !== "todo") {
      return { char: "-", start: dashMatch.index!, query: name }
    }
  }

  // Bare -- with no following chars (show all folders, useful on mobile)
  if (beforeCaret.endsWith("--") && !beforeCaret.endsWith("---")) {
    return { char: "-", start: beforeCaret.length - 2, query: "" }
  }

  for (let i = caret - 1; i >= 0; i--) {
    const c = text[i]
    if (c === ">" || c === "}" || c === " " || c === "\n" || c === "\t") {
      return null
    }
    if (c === "<" || c === "{" || c === "\\") {
      const query = text.slice(i + 1, caret)
      if (c === "\\") {
        if (!/^[\p{L}\p{N}\p{M}-]*$/u.test(query)) return null
      }
      return { char: c as "<" | "{" | "\\", start: i, query }
    }
  }
  return null
}
