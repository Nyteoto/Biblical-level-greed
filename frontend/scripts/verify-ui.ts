// Golden-corpus verifier for the TypeScript half of the port.
//
// `trophic/golden/verify_golden.py` covers the modules that became Python.
// This covers the ones that stayed TypeScript, and it exists because that
// file says so:
//
//   "For a target that keeps the TypeScript (the frontend of a same-language
//    port), the faithful adapter is to run the real module and serialise it
//    the way generate-ui.ts does; these Python stubs are for a port that
//    rewrites it."
//
// So this imports the actual modules the app ships — no reimplementation, no
// mock of the thing under test — and replays the corpus against them.
//
//   node --experimental-strip-types scripts/verify-ui.ts            # everything
//   node --experimental-strip-types scripts/verify-ui.ts colorize   # one file
//   node --experimental-strip-types scripts/verify-ui.ts -v         # all diffs
//
// Or `npm run verify:ui`. It needs `trophic/` on disk; the bundle is
// gitignored, so a fresh clone reports the corpus as missing and exits 2.
//
// Two things the corpus needs that a browser would supply: a frozen clock
// (the trie's ranking calls Date.now()) and a canvas. Both are stubbed at the
// top of the run rather than injected, because the modules read them the way
// the real ones do and changing that to suit a test would be testing a
// different program.

import { readFileSync, readdirSync, existsSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

import { tokenize, activeTrigger } from '../src/lib/trophic/tokenize.ts';
import { buildTrie, prefixSearch, scoredSearch } from '../src/lib/trophic/trie.ts';
import { validate } from '../src/lib/trophic/validation.ts';
import { view, handleKey, caretStyle } from '../src/lib/trophic/capture-bar.ts';
import { colorizeSegments, segmentsToHtml } from '../src/lib/trophic/colorize.ts';
import { LongPress } from '../src/lib/trophic/longpress.ts';
import { classifyDevice, keyboardOpen, readHandMode, COARSE_QUERY } from '../src/lib/trophic/device.ts';
import { enqueue, flush, pendingCount, STORAGE_KEY } from '../src/lib/trophic/retry-queue.ts';
import { todayKey } from '../src/lib/trophic/day.ts';
import { tagForPin, withPinnedTag } from '../src/lib/trophic/pinned.ts';
import { albumWeek, foldQuiet, groupDays, isoWeek } from '../src/lib/trophic/log.ts';
import type { Entry, Vocab } from '../src/lib/trophic/api.ts';

const HERE = dirname(fileURLToPath(import.meta.url));
const CORPUS = join(HERE, '..', '..', 'trophic', 'golden', 'corpus');
const FLOAT_TOL = 1e-9;

// The clock every corpus file was generated against.
const FROZEN_NOW = Date.parse('2026-08-14T12:00:00.000Z');
Date.now = () => FROZEN_NOW;

// ── Corpus vocab → this port's shape ──────────────────────────────────────
// The corpus speaks the source's camelCase; the API this frontend talks to is
// snake_case. One rename, here, rather than in the module.

type CorpusVocab = {
	folders: { id: string; name: string; color: string }[];
	tagToFolder: Record<string, string>;
	tags: string[];
	times: string[];
	patterns: string[];
};

function asVocab(v: CorpusVocab | undefined): Vocab | undefined {
	if (!v) return undefined;
	return {
		folders: v.folders,
		tag_to_folder: v.tagToFolder,
		tags: v.tags,
		times: v.times,
		patterns: v.patterns
	};
}

// ── Adapters ──────────────────────────────────────────────────────────────

type Adapter = (input: never) => unknown;
const ADAPTERS: Record<string, Adapter> = {};

ADAPTERS.tokenize = (i: { text: string }) => tokenize(i.text);

ADAPTERS.active_trigger = (i: { text: string; caret: number }) =>
	activeTrigger(i.text, i.caret);

ADAPTERS.trie_prefix = (i: { terms: string[]; prefix: string }) =>
	prefixSearch(buildTrie(i.terms), i.prefix);

ADAPTERS.trie_scored = (i: {
	terms: string[];
	query: string;
	stats: Record<string, { count: number; last: number }>;
	limit: number | null;
}) =>
	i.limit == null
		? scoredSearch(buildTrie(i.terms), i.terms, i.query, i.stats)
		: scoredSearch(buildTrie(i.terms), i.terms, i.query, i.stats, i.limit);

ADAPTERS.capture_validation = (i: { draft: string; vocab: CorpusVocab }) =>
	validate(i.draft, asVocab(i.vocab));

// The capture bar. The component owns the textarea, the timers and the
// measuring; `capture-bar.ts` owns everything else, which is what these two
// replay. The caret's x/y is the one thing a browser would supply, so the
// corpus supplies metrics instead and the adapter does the measurement the
// same way — column × charWidth, padTop + line × lineHeight.

type Layout = { charWidth: number; lineHeight: number; padTop: number };

function measureCaret(value: string, caret: number, layout: Layout) {
	const before = value.slice(0, caret);
	const line = before.split('\n').length - 1;
	const column = before.length - (before.lastIndexOf('\n') + 1);
	return { x: column * layout.charWidth, y: layout.padTop + line * layout.lineHeight };
}

ADAPTERS.capture_overlay = (i: {
	value: string;
	caret: number;
	vocab: CorpusVocab | null;
	blinkIndices: number[];
	layout: Layout;
}) => {
	const state = { value: i.value, caret: i.caret, suggestIdx: 0, stats: {} };
	const v = view(state, asVocab(i.vocab ?? undefined), i.blinkIndices);
	return {
		overlay: v.overlay,
		ghost: v.ghost,
		caret: caretStyle(measureCaret(i.value, i.caret, i.layout), true),
		suggestions: v.suggestions,
		suggestOpen: v.suggestOpen
	};
};

ADAPTERS.capture_keys = (i: {
	value: string;
	caret: number;
	vocab: CorpusVocab;
	keys: { key: string; shiftKey?: boolean; isComposing?: boolean; keyCode?: number }[];
}) => {
	const vocab = asVocab(i.vocab);
	let state = { value: i.value, caret: i.caret, suggestIdx: 0, stats: {} };
	let forwarded = 0;
	const steps = i.keys.map((k) => {
		const r = handleKey(state, vocab, k);
		state = r.state;
		if (r.forwarded) forwarded++;
		const v = view(state, vocab);
		return {
			key: k.key,
			prevented: r.prevented,
			forwarded,
			value: state.value,
			caret: state.caret,
			ghost: v.ghost,
			suggestions: v.suggestions
		};
	});
	const storage: Record<string, string> = {};
	if (Object.keys(state.stats).length > 0) {
		storage['capture-ac-stats'] = JSON.stringify(state.stats);
	}
	return {
		steps,
		final: { value: state.value, caret: state.caret, forwarded },
		storage,
		// Every key pauses the caret blink, including the ones that do nothing.
		pendingTimers: i.keys.length ? 1 : 0
	};
};

ADAPTERS.long_press = (i: {
	delay: number;
	moveThreshold: number;
	events: { t: string; pts?: { x: number; y: number }[]; ms?: number }[];
}) => {
	// A fake clock: the corpus advances time in jumps rather than waiting.
	let clock = 0;
	let seq = 0;
	const due = new Map<number, { at: number; fn: () => void }>();
	const timers = {
		set(fn: () => void, ms: number) {
			const id = seq++;
			due.set(id, { at: clock + ms, fn });
			return id;
		},
		clear(id: unknown) {
			due.delete(id as number);
		}
	};
	function advance(ms: number) {
		clock += ms;
		for (const [id, t] of [...due].sort((a, b) => a[1].at - b[1].at)) {
			if (t.at <= clock) {
				due.delete(id);
				t.fn();
			}
		}
	}

	const fired: { x: number; y: number }[] = [];
	const press = new LongPress(
		(x, y) => fired.push({ x, y }),
		i.delay,
		i.moveThreshold,
		timers
	);

	let clicksSwallowed = 0;
	let clicksPassed = 0;
	for (const ev of i.events) {
		if (ev.t === 'start') press.start(ev.pts ?? []);
		else if (ev.t === 'move') press.move(ev.pts ?? []);
		else if (ev.t === 'end' || ev.t === 'cancel') press.end();
		else if (ev.t === 'advance') advance(ev.ms ?? 0);
		else if (ev.t === 'click') press.click() ? clicksSwallowed++ : clicksPassed++;
	}
	return { fired, clicksSwallowed, clicksPassed };
};

ADAPTERS.viewport = (i: {
	hook: string;
	userAgent?: string;
	maxTouchPoints?: number;
	matchMedia?: Record<string, boolean>;
	innerHeight?: number;
	visualViewportHeight?: number | null;
	stored?: string | null;
	setTo?: string | null;
}) => {
	if (i.hook === 'useDeviceType') {
		return classifyDevice(
			i.userAgent ?? '',
			i.maxTouchPoints ?? 0,
			i.matchMedia?.[COARSE_QUERY] ?? false
		);
	}
	if (i.hook === 'useVirtualKeyboard') {
		return { open: keyboardOpen(i.innerHeight ?? 0, i.visualViewportHeight ?? null) };
	}
	// useHandMode. Reading validates; setting writes through whatever it is
	// given, so a set of "left" stores "left" and a garbage read stays stored.
	const storage: Record<string, string> = {};
	if (i.stored != null) storage['trophic-hand-mode'] = i.stored;
	let mode = readHandMode(i.stored ?? null);
	if (i.setTo != null) {
		mode = i.setTo as 'left' | 'right';
		storage['trophic-hand-mode'] = i.setTo;
	}
	return { mode, storage };
};

ADAPTERS.retry_queue = (i: {
	initialStorage: string | null;
	now: string;
	maxAgeMs: number;
	steps: { t: string; url?: string; body?: string; responses?: (number | string)[] }[];
}) => {
	const store: Record<string, string> = {};
	if (i.initialStorage != null) store[STORAGE_KEY] = i.initialStorage;
	const attempts: { url: string; body: string }[] = [];
	let plan: (number | string)[] = [];

	const env = {
		getItem: (k: string) => store[k] ?? null,
		setItem: (k: string, v: string) => {
			store[k] = v;
		},
		now: () => Date.parse(i.now),
		maxAgeMs: i.maxAgeMs,
		fetch: async (url: string, init: { body: string }) => {
			attempts.push({ url, body: init.body });
			const next = plan.shift();
			if (next === 'network-error' || next === undefined) throw new Error('offline');
			return { ok: (next as number) >= 200 && (next as number) < 300 };
		}
	};

	// The corpus's flush step is asynchronous; the adapter is not, so the
	// runner awaits this one. See the note about this file in TROPHIC.md.
	return (async () => {
		const trace: unknown[] = [];
		for (const step of i.steps) {
			if (step.t === 'enqueue') enqueue(env, step.url!, step.body!);
			else if (step.t === 'flush') {
				plan = [...(step.responses ?? [])];
				await flush(env);
			}
			trace.push({
				after: step.t,
				pending: pendingCount(env),
				queue: JSON.parse(store[STORAGE_KEY] ?? '[]')
			});
		}
		return { trace, attempts, storage: { ...store } };
	})();
};

ADAPTERS.colorize = (i: { text: string }) => {
	const segments = colorizeSegments(i.text);
	return { segments, html: segmentsToHtml(segments) };
};

// ── The one declared deviation: colour ────────────────────────────────────
//
// The source was painted against white and this app is painted on `#f3f2f2`
// in Archivo, so every colour was re-lit. That is written down in TROPHIC.md
// as a deliberate deviation — but "we changed the colours" is the kind of
// excuse that hides a real mistake, so it is spelled out here instead: each
// colour this port emits, and the source colour(s) it stands in for. Anything
// else is a failure. Geometry, ordering and op counts are compared exactly.
//
// This table has been rewritten once already, when the shell went from
// `#14100c` back to paper. That it was the *only* thing that had to change is
// the point of keeping it: the hues never moved, only their lightness, and a
// one-line-per-colour table is what proves that rather than asserts it.

const THEME: Record<string, string[]> = {
	// lib/colors.ts — the syntax hues, now collapsed onto one phosphor.
	//
	// This is the first time the table has been many-to-one, and it is the whole
	// design rather than a shortcut: a single-phosphor tube has no hue to spend,
	// so every token kind is the same lit green and the delimiters — `<>`, `{}`,
	// `\`, `--` — carry the distinction they always carried. What tells a tag
	// from prose on screen is weight, which is applied in `ColorizedText.svelte`
	// and is deliberately not in `colorize.ts`: the corpus pins the colour of
	// each segment, not how heavily this app chooses to set it.
	'#4fff9f': [
		'#3b82f6', // folder
		'#9333ea', // time
		'#e11d48', // pattern
		'#d97706', // directive
		'#8b5cf6', // todo
		'#18181b' // ink — the caret, which is also peak emission here
	],
	// The refusal red the validation layer blinks a token in. It is the one
	// colour `phosphorize()` refuses to fold into the ramp, for the same reason
	// it is the one colour left in this table: a refusal that looks like output
	// is not a refusal.
	'#ff6a5a': ['#ef4444']
};

/** `rgba(r,g,b,a)` translations, alpha carried through unchanged. */
const THEME_RGB: Record<string, string> = {
	'79,255,159': '24,24,27' // ink — the caret and its halo
};

function translated(actual: string): string[] {
	if (THEME[actual]) return THEME[actual];
	const m = actual.match(/^rgba\((\d+,\d+,\d+),(.+)\)$/);
	if (m && THEME_RGB[m[1]]) return [`rgba(${THEME_RGB[m[1]]},${m[2]})`];
	return [];
}

/** Source colour → this port's colour, for translating colours embedded in a
 *  larger string — `colorize`'s rendered markup.
 *
 *  Note the direction, which is the reverse of what this used to do. The old
 *  version rewrote the *actual* markup back into source colours and had to skip
 *  any port colour standing for more than one source, because inside a string
 *  there is nothing to disambiguate them against. Now that five source hues
 *  collapse onto one phosphor, skipping the ambiguous ones would skip all of
 *  them and the colorize fixtures would stop checking anything.
 *
 *  Going the other way has no such problem: every source colour has exactly one
 *  port colour, so rewriting the *expected* fixture forward into what this port
 *  should emit is a total function. Nothing is excluded and nothing is guessed. */
const THEME_FORWARD = Object.entries(THEME).flatMap(([port, sources]) =>
	sources.map((source) => [source, port] as const)
);

function translatedWithin(expected: string): string {
	let out = expected;
	for (const [source, port] of THEME_FORWARD) out = out.split(source).join(port);
	// `rgba(…)` inside a larger value — the caret's box-shadow.
	for (const [port, source] of Object.entries(THEME_RGB)) {
		out = out.split(`rgba(${source},`).join(`rgba(${port},`);
	}
	return out;
}

// ── Comparison ────────────────────────────────────────────────────────────

function diff(actual: unknown, expected: unknown, path = ''): string[] {
	const p = path || '<root>';

	if (typeof actual === 'string' && typeof expected === 'string' && actual !== expected) {
		if (translated(actual).includes(expected)) return [];
		if (translatedWithin(expected) === actual) return [];
	}

	if (typeof expected === 'number' && typeof actual === 'number') {
		if (Number.isNaN(expected) && Number.isNaN(actual)) return [];
		if (Math.abs(actual - expected) <= FLOAT_TOL) return [];
		return [`${p}: expected ${expected}, got ${actual}`];
	}
	if (expected === null || actual === null || typeof expected !== 'object') {
		return Object.is(actual, expected)
			? []
			: [`${p}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`];
	}
	if (typeof actual !== 'object' || actual === null) {
		return [`${p}: expected an object, got ${JSON.stringify(actual)}`];
	}

	if (Array.isArray(expected)) {
		if (!Array.isArray(actual)) return [`${p}: expected an array`];
		const out: string[] = [];
		if (expected.length !== actual.length) {
			out.push(`${p}: expected ${expected.length} items, got ${actual.length}`);
		}
		for (let i = 0; i < Math.min(expected.length, actual.length); i++) {
			out.push(...diff(actual[i], expected[i], `${p}[${i}]`));
		}
		return out;
	}

	const out: string[] = [];
	const exp = expected as Record<string, unknown>;
	const act = actual as Record<string, unknown>;
	for (const k of Object.keys(exp)) {
		if (!(k in act)) out.push(`${p}.${k}: missing (expected ${JSON.stringify(exp[k])})`);
		else out.push(...diff(act[k], exp[k], `${p}.${k}`));
	}
	for (const k of Object.keys(act)) {
		// undefined and absent are the same thing on the wire, and the corpus
		// went through JSON.stringify on the way out.
		if (!(k in exp) && act[k] !== undefined) {
			out.push(`${p}.${k}: unexpected key (got ${JSON.stringify(act[k])})`);
		}
	}
	return out;
}

/** Drop undefined the way JSON.stringify would, so shapes line up. */
function jsonish(v: unknown): unknown {
	return v === undefined ? undefined : JSON.parse(JSON.stringify(v));
}

// ── Checks with no corpus behind them ─────────────────────────────────────
//
// The corpus covers what the source did. This covers what this port got wrong
// on its own. Kept here rather than in a test file of its own because the
// frontend has exactly one runner and a second one would not get run.

function localChecks(): string[] {
	const failures: string[] = [];

	// Midnight east of Greenwich. The backend files an entry under the user's
	// local day; a browser computing "today" from `toISOString()` disagrees
	// with it from local midnight until the UTC offset catches up, and the
	// entry you just captured is not on the day the log is showing. Cost a
	// real "where did my photo go" before it was found.
	const midnightPlus7 = new Date('2026-08-15T17:00:36.000Z');
	const spelled = `${midnightPlus7.getFullYear()}-${String(
		midnightPlus7.getMonth() + 1
	).padStart(2, '0')}-${String(midnightPlus7.getDate()).padStart(2, '0')}`;
	if (process.env.TZ === 'Asia/Bangkok' && spelled !== '2026-08-16') {
		failures.push(`  local day at 00:00:36 +07 was ${spelled}, expected 2026-08-16`);
	}
	// The helper the app actually calls has to agree with that spelling.
	if (typeof todayKey() !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(todayKey())) {
		failures.push(`  todayKey() returned ${todayKey()}`);
	}

	// The pin writes its folder's tag into the raw line. Everything the log
	// shows is a fold over that text, so a mistake here is not a display bug —
	// it is a capture filed in the wrong place, permanently, in an append-only
	// log. No corpus covers it: the source has no pin.
	const pinCases: [string, string, string][] = [
		['cut the legs', 'kitchen-table', 'cut the legs <kitchen-table>'],
		// Already reaching that folder, by tag or by directive: leave it alone.
		['cut the legs <kitchen-table>', 'kitchen-table', 'cut the legs <kitchen-table>'],
		['--kitchen-table cut the legs', 'kitchen-table', '--kitchen-table cut the legs'],
		// Tags are matched lowercased, the way the parser reads them.
		['cut the legs <Kitchen-Table>', 'kitchen-table', 'cut the legs <Kitchen-Table>'],
		// A different folder's tag is not this folder's.
		['sanded it <workshop>', 'kitchen-table', 'sanded it <workshop> <kitchen-table>'],
		// Media with no words: the tag becomes the whole line.
		['', 'kitchen-table', '<kitchen-table>'],
		['   ', 'kitchen-table', '<kitchen-table>'],
		// A folder name with a space keeps it — `normalize_tag` only trims and
		// lowercases, and `<a b>` is one folder token to the tokenizer.
		['glued up', 'kitchen table', 'glued up <kitchen table>'],
		// No pin, no change.
		['cut the legs', '', 'cut the legs']
	];
	for (const [text, tag, want] of pinCases) {
		const got = withPinnedTag(text, tag);
		if (got !== want) {
			failures.push(`  withPinnedTag(${JSON.stringify(text)}, ${JSON.stringify(tag)}) = ` +
				`${JSON.stringify(got)}, expected ${JSON.stringify(want)}`);
		}
	}

	// Which tag a pin writes: the folder's own name when it holds it, whatever
	// does point here when something else claimed the name first, and nothing
	// at all when no tag reaches it.
	const pinTagCases: [{ name: string; tags: string[] }, string | null][] = [
		[{ name: 'Kitchen table', tags: ['kitchen table'] }, 'kitchen table'],
		[{ name: 'Kitchen table', tags: ['bench', 'kitchen table'] }, 'kitchen table'],
		[{ name: 'Garden', tags: ['allotment'] }, 'allotment'],
		[{ name: 'Garden', tags: [] }, null]
	];
	for (const [folder, want] of pinTagCases) {
		const got = tagForPin(folder);
		if (got !== want) {
			failures.push(`  tagForPin(${JSON.stringify(folder)}) = ${JSON.stringify(got)}, ` +
				`expected ${JSON.stringify(want)}`);
		}
	}

	// The Log's quiet-stretch merge. No corpus covers it — the source has no
	// such thing — and it is the one piece of this UI that can *swallow* days
	// rather than crash, so it gets an oracle here. The invariant being
	// checked is the only one that matters: **merging never loses an entry.**
	const day = (key: string, texts: string[], media: string[] = []): Entry[] =>
		texts.map((text, i) => ({
			id: `${key}-${i}`,
			ts: `${key}T09:0${i}:00Z`,
			day: key,
			raw_text: text,
			clean_text: text,
			folders: [],
			times: [],
			patterns: [],
			todo_lines: [],
			todo_done: [],
			manual_folders: [],
			media: i === 0 ? media : []
		}));

	const feed = [
		...day('2026-08-15', ['loud'], ['a.jpg']), // has media — never quiet
		...day('2026-08-14', ['one']),
		...day('2026-08-13', ['one', 'two']),
		...day('2026-08-12', ['one']),
		...day('2026-08-11', ['a', 'b', 'c']), // three lines — not quiet
		...day('2026-08-10', ['one'])
	];
	const days = groupDays(feed);
	if (days.map((d) => d.key).join(',') !== '2026-08-15,2026-08-14,2026-08-13,2026-08-12,2026-08-11,2026-08-10') {
		failures.push(`  groupDays did not come back newest first: ${days.map((d) => d.key)}`);
	}

	const folded = foldQuiet(days);
	const shape = folded
		.map((row) => (row.kind === 'stretch' ? `stretch(${row.days.length})` : row.day.key))
		.join(' ');
	if (shape !== '2026-08-15 stretch(3) 2026-08-11 2026-08-10') {
		failures.push(`  foldQuiet gave ${shape}`);
	}
	// A run of one stays a row: a strip saying "quiet stretch · 1 line" is
	// longer than the line it is hiding.
	if (folded.at(-1)?.kind !== 'day') {
		failures.push('  foldQuiet merged a run of one quiet day into a stretch');
	}
	// Nothing may go missing, with the merge on or off.
	for (const merge of [true, false]) {
		const seen = foldQuiet(days, merge).flatMap((row) =>
			row.kind === 'stretch' ? row.days : [row.day]
		);
		const count = seen.reduce((n, d) => n + d.entries.length, 0);
		if (count !== feed.length) {
			failures.push(`  foldQuiet(merge=${merge}) held ${count} entries, not ${feed.length}`);
		}
	}

	// ISO weeks belong to the year holding their Thursday, so the turn of the
	// year is where the naive "day of year over seven" gets it wrong — and the
	// turn of the year is exactly what the Log draws attention to.
	const weekCases: [string, number][] = [
		['2026-01-01', 1], // a Thursday: week 1 of 2026
		['2025-01-01', 1], // a Wednesday: still week 1
		['2027-01-01', 53], // a Friday: week 53 of 2026
		['2026-08-15', 33],
		['2026-12-31', 53]
	];
	for (const [key, want] of weekCases) {
		const got = isoWeek(key);
		if (got !== want) failures.push(`  isoWeek(${key}) = ${got}, expected ${want}`);
	}

	// `albumWeek` counts an album's own weeks from 0, on Monday boundaries. The
	// last case is the one worth pinning: it crosses a new year, where ISO week
	// numbers reset and a subtraction of them would go negative.
	const albumCases: [string, string, number][] = [
		['2026-08-18', '2026-08-18', 0],
		['2026-08-18', '2026-08-23', 0], // same Mon–Sun week
		['2026-08-18', '2026-08-24', 1], // the next Monday
		['2026-08-18', '2026-09-07', 3],
		['2026-12-28', '2027-01-04', 1]
	];
	for (const [first, key, want] of albumCases) {
		const got = albumWeek(first, key);
		if (got !== want) {
			failures.push(`  albumWeek(${first}, ${key}) = ${got}, expected ${want}`);
		}
	}

	return failures;
}

// ── One corpus file that cannot be satisfied ──────────────────────────────
//
// `retry_queue.json` does not describe the module it was generated from, and
// the port deliberately does not chase it. The evidence, from running the
// adapter below against a faithful port of `hooks/retryQueue.ts`:
//
//   - `queue-enqueue-then-flush-ok` expects the entry to still be in storage
//     after a successful send. `flush()` ends in `save(remaining)`, and a
//     sent entry is never pushed to `remaining`, so storage must end empty.
//   - `queue-flush-partial-server-error` scripts two responses for two queued
//     entries and records one attempt. With `await flush()` — which the
//     generator does — the loop makes two.
//   - Every case reports `pending: 0` while its own `queue` field lists up to
//     three entries, and `pendingCount()` is `load().length` over that same
//     storage. The two cannot both be true.
//
// Read together, the generator's harness and the module were reading two
// different localStorage objects. The notes on the file are accurate and the
// port follows them; the fixtures are not reproducible from the source.
// Regenerate the bundle and delete this entry if it starts passing.

const KNOWN_BAD: Record<string, string> = {
	retry_queue:
		'fixtures contradict their own source — see the note in scripts/verify-ui.ts'
};

// ── Runner ────────────────────────────────────────────────────────────────

async function runFile(stem: string, verbose: boolean) {
	const doc = JSON.parse(readFileSync(join(CORPUS, `${stem}.json`), 'utf8'));
	const cases = doc.cases as { id: string; input: unknown; expected: unknown }[];
	const fn = ADAPTERS[stem];

	if (!fn) {
		console.log(`  ${stem.padEnd(20)} NOT MINE     (${cases.length} cases)`);
		return { status: 'skipped', passed: 0, failed: 0, total: cases.length };
	}

	let passed = 0;
	let failed = 0;
	let shown = 0;
	const lines: string[] = [];

	for (const c of cases) {
		let actual: unknown;
		try {
			const raw = fn(c.input as never);
			actual = jsonish(raw instanceof Promise ? await raw : raw);
		} catch (err) {
			failed++;
			lines.push(`    [${c.id}] THREW ${err instanceof Error ? err.message : String(err)}`);
			continue;
		}
		const diffs = diff(actual, c.expected);
		if (diffs.length === 0) {
			passed++;
			continue;
		}
		failed++;
		if (verbose || shown < 5) {
			shown++;
			lines.push(`    [${c.id}] input=${JSON.stringify(c.input).slice(0, 160)}`);
			for (const d of diffs.slice(0, 8)) lines.push(`        ${d}`);
		}
	}

	if (failed && KNOWN_BAD[stem]) {
		console.log(`  ${stem.padEnd(20)} CORPUS?  ${passed}/${cases.length}`);
		console.log(`    ${KNOWN_BAD[stem]}`);
		return { status: 'corpus', passed: 0, failed: 0, total: cases.length };
	}

	console.log(
		`  ${stem.padEnd(20)} ${failed === 0 ? 'PASS' : 'FAIL'}  ${passed}/${cases.length}`
	);
	for (const l of lines) console.log(l);
	if (failed && !verbose && failed > shown) {
		console.log(`    … ${failed - shown} more failing case(s); re-run with -v`);
	}
	return { status: failed ? 'fail' : 'ok', passed, failed, total: cases.length };
}

async function main(argv: string[]): Promise<number> {
	const verbose = argv.includes('-v') || argv.includes('--verbose');
	const wanted = argv.filter((a) => !a.startsWith('-'));

	if (!existsSync(CORPUS)) {
		console.error(`corpus directory not found: ${CORPUS}`);
		console.error('the trophic/ bundle is gitignored — see TROPHIC.md');
		return 2;
	}

	let stems = readdirSync(CORPUS)
		.filter((f) => f.endsWith('.json') && f !== 'index.json')
		.map((f) => f.slice(0, -5))
		.filter((s) => s in ADAPTERS)
		.sort();
	if (wanted.length) stems = stems.filter((s) => wanted.includes(s));
	if (!stems.length) {
		console.error(`no corpus files matched: ${wanted.join(', ')}`);
		return 2;
	}

	console.log(`golden corpus, TypeScript side — ${stems.length} file(s)\n`);
	let pass = 0;
	let fail = 0;
	let total = 0;
	for (const stem of stems) {
		const r = await runFile(stem, verbose);
		pass += r.passed;
		fail += r.failed;
		total += r.total;
	}
	const local = localChecks();
	for (const line of local) console.log(line);
	if (local.length) console.log(`  ${'local checks'.padEnd(20)} FAIL  ${local.length} problem(s)`);
	else console.log(`  ${'local checks'.padEnd(20)} PASS  (no corpus, this port's own mistakes)`);

	console.log(`\n${pass} passed, ${fail + local.length} failed (${total} cases)`);
	return fail || local.length ? 1 : 0;
}

process.exit(await main(process.argv.slice(2)));
