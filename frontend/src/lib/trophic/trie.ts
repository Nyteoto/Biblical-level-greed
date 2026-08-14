// Trie-based autocomplete with MRU/MFU scoring.
//
// Copied verbatim from `trophic/reference/logic/trie.ts` — see the note at the
// top of tokenize.ts for why a same-language port is a copy. The one thing to
// resist: `prefixSearch` walks `Object.values(children)`, so results come back
// in insertion order rather than sorted. That is deliberate and the corpus
// pins it.
//
// `loadStats`/`saveStats` keep usage counts in localStorage. That is the one
// piece of state in this app that is not in the log, and it is fine there:
// it ranks a dropdown, and losing it costs a few keystrokes.

// ── Trie data structure ──

interface TrieNode {
  c: Record<string, TrieNode> // children
  t: string[] // terminal terms ending at this node
}

function node(): TrieNode {
  return { c: {}, t: [] }
}

export function buildTrie(terms: string[]): TrieNode {
  const root = node()
  for (const term of terms) {
    // In encrypted mode, vocab can briefly hold undefined folder names while
    // the worker is locked (decode can't decrypt nameCipher). Skip rather
    // than crash; the next decode pass after unlock fills them in.
    if (typeof term !== "string" || term.length === 0) continue
    let n = root
    for (const ch of term.toLowerCase()) {
      n.c[ch] ??= node()
      n = n.c[ch]
    }
    n.t.push(term)
  }
  return root
}

function collect(n: TrieNode, out: string[]) {
  out.push(...n.t)
  for (const child of Object.values(n.c)) collect(child, out)
}

export function prefixSearch(root: TrieNode, prefix: string): string[] {
  let n = root
  for (const ch of prefix.toLowerCase()) {
    if (!n.c[ch]) return []
    n = n.c[ch]
  }
  const out: string[] = []
  collect(n, out)
  return out
}

// ── MRU / MFU stats ──

export interface UsageEntry {
  count: number
  last: number
}
export type UsageStats = Record<string, UsageEntry>

const STORAGE_KEY = "capture-ac-stats"
const DECAY_MS = 7 * 86_400_000 // 7-day window for recency

export function loadStats(): UsageStats {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}")
  } catch {
    return {}
  }
}

export function saveStats(s: UsageStats) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
  } catch {}
}

export function recordUse(s: UsageStats, term: string): UsageStats {
  const k = term.toLowerCase()
  const prev = s[k] ?? { count: 0, last: 0 }
  return { ...s, [k]: { count: prev.count + 1, last: Date.now() } }
}

function score(term: string, stats: UsageStats): number {
  const e = stats[term.toLowerCase()]
  if (!e) return 0
  const recency = Math.max(0, 1 - (Date.now() - e.last) / DECAY_MS)
  // Frequency weight 2× + recency boost 10× (recent items float to top)
  return e.count * 2 + recency * 10
}

/**
 * Prefix matches via Trie, then contains-but-not-prefix via linear scan.
 * Results sorted by MRU/MFU score within each tier.
 * Empty query returns all terms sorted by score.
 */
export function scoredSearch(
  root: TrieNode,
  all: string[],
  query: string,
  stats: UsageStats,
  limit = 8,
): string[] {
  const byScore = (a: string, b: string) => score(b, stats) - score(a, stats)

  if (!query) {
    return [...all].sort(byScore).slice(0, limit)
  }

  const q = query.toLowerCase()
  const prefixSet = new Set(prefixSearch(root, q))
  const contains = all.filter(
    (t) => !prefixSet.has(t) && t.toLowerCase().includes(q),
  )

  return [
    ...[...prefixSet].sort(byScore),
    ...contains.sort(byScore),
  ].slice(0, limit)
}
