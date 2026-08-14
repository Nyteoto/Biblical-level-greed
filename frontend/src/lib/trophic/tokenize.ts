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

export type TokenKind = "folder" | "time" | "pattern" | "directive" | "todo" | "text"

export type Token = {
  kind: TokenKind
  start: number
  end: number
  raw: string
  value: string // inner content, lowercased (empty for "text")
}

// Navigation commands that are full-line, not inline directives
const NAV_COMMANDS = new Set([
  "codex", "folders", "settings", "assign", "logout", "dev", "draw",
])

const PATTERNS: { kind: Exclude<TokenKind, "text">; re: RegExp; group?: number; filter?: (value: string) => boolean }[] = [
  { kind: "folder", re: /<([^<>]+)>/g },
  { kind: "time", re: /\{([^{}]+)\}/g },
  // Unicode-aware: accept letters + numbers + combining marks in any script.
  { kind: "pattern", re: /\\([\p{L}\p{N}\p{M}]+(?:-[\p{L}\p{N}\p{M}]+)*)/gu },
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

export function tokenize(text: string): Token[] {
  const quoted = quotedRanges(text)
  const matches: Token[] = []

  for (const { kind, re, filter } of PATTERNS) {
    for (const m of text.matchAll(re)) {
      // Skip patterns inside quoted strings
      if (kind === "pattern" && inQuoted(m.index!, quoted)) continue
      // Skip escaped backslash (`\ `)
      if (kind === "pattern" && isEscapedBackslash(text, m.index!)) continue

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
