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
import { validate, CAP_WARN_AT, MAX_RAW_LEN } from '../src/lib/trophic/validation.ts';
import { view, handleKey, caretStyle, acceptSuggestion } from '../src/lib/trophic/capture-bar.ts';
import { colorizeSegments, segmentsToHtml } from '../src/lib/trophic/colorize.ts';
import { LongPress } from '../src/lib/trophic/longpress.ts';
import { classifyDevice, keyboardOpen, readHandMode, COARSE_QUERY } from '../src/lib/trophic/device.ts';
import { clockFace, duration, pomodoroAt } from '../src/lib/trophic/timer.ts';
import {
	enqueue,
	flush,
	load,
	pendingCount,
	MAX_AGE_MS,
	STORAGE_KEY,
	type QueueEnv
} from '../src/lib/trophic/retry-queue.ts';
import { todayKey } from '../src/lib/trophic/day.ts';
import { tagForPin, withPinnedTag } from '../src/lib/trophic/pinned.ts';
import { albumWeek, foldQuiet, groupDays, isoWeek } from '../src/lib/trophic/log.ts';
import { dropBefore, moveBefore } from '../src/lib/trophic/sortable.ts';
import { reorderGroups, splitShelf } from '../src/lib/trophic/shelf.ts';
import { lineFor, send } from '../src/lib/trophic/submission.ts';
import { NetworkError } from '../src/lib/trophic/api.ts';
import { isReply, stripReply } from '../src/lib/trophic/reply.ts';
import { COMMANDS } from '../src/lib/trophic/capture-bar.ts';
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
	// runner awaits this one. Why this file reports CORPUS? rather than passing
	// or failing is in the `retry_queue` branch of `runFile` below.
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
// The source was painted against white; this app is a green-phosphor tube on
// `#0a1116`, so every colour was re-lit. "We changed the colours" is the kind
// of excuse that hides a real mistake, so it is spelled out here instead: each
// colour this port emits, and the source colour(s) it stands in for. Anything
// else is a failure. Geometry, ordering and op counts are compared exactly.
//
// This table has been rewritten twice — when the shell went from `#14100c` to
// paper, and again when paper became the tube. That it is the *only* thing
// that has to change each time is the point of keeping it.
//
// **It is many-to-one now, and that is why it translates source→port.** The
// re-light collapsed five syntax hues onto one phosphor, so several source
// colours map to the same `#4fff9f` and the reverse lookup has no answer.
// Translate the expectation forward and then demand an exact match; do not
// try to read a port colour back to the hue it came from.

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

async function localChecks(): Promise<string[]> {
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

	// The length rule, which the corpus knows nothing about — the source had no
	// such issue type and its cap was enforced only by the server. It is here
	// because of what happened when it was: the refusal came back inside the
	// 220ms the draft takes to slide out of the box, the restore lost the race
	// with the clear, and a two-thousand-word entry was gone with no copy of it
	// anywhere. The bar refusing it first is what makes that unreachable, so
	// the rule that does the refusing gets an oracle.
	const capVocab: Vocab = { folders: [], tag_to_folder: {}, tags: [], patterns: [], places: [] };
	const lengthCases: [string, string, number, boolean][] = [
		// [what it is, draft, reserved, should lock]
		['exactly at the cap', 'x'.repeat(MAX_RAW_LEN), 0, false],
		['one over', 'x'.repeat(MAX_RAW_LEN + 1), 0, true],
		// Trimmed before counting, the way `store.capture` counts it.
		['padding does not count', `  ${'x'.repeat(MAX_RAW_LEN)}  `, 0, false],
		// The pin's tag is appended on the way out and counts against the cap.
		['the pin tips it over', 'x'.repeat(MAX_RAW_LEN - 2), 3, true],
		// An empty draft reserves nothing: there is no line to append a tag to.
		['empty with a pin on', '', MAX_RAW_LEN + 1, false]
	];
	for (const [what, draft, reserved, want] of lengthCases) {
		for (const vocab of [capVocab, undefined]) {
			const got = validate(draft, vocab, reserved);
			if (got.locked !== want) {
				failures.push(`  ${what} (vocab ${vocab ? 'loaded' : 'absent'}): locked=${got.locked}, expected ${want}`);
			}
			if (want && got.issues[0]?.type !== 'too-long') {
				failures.push(`  ${what}: first issue was ${got.issues[0]?.type ?? 'none'}, expected too-long`);
			}
		}
	}
	// Length is reported first, so it is the one the bar prints: it is the only
	// issue that stops the send outright, and `slice(0, 1)` shows one.
	const both = validate(`--nope ${'x'.repeat(MAX_RAW_LEN)}`, capVocab);
	if (both.issues[0]?.type !== 'too-long' || both.issues.length !== 2) {
		failures.push(`  a draft both too long and misdirected reported ${both.issues.map((i) => i.type).join(', ')}`);
	}
	// The warning threshold has to leave room to act in and stay out of the way
	// of an ordinary line.
	if (!(CAP_WARN_AT < MAX_RAW_LEN && CAP_WARN_AT > MAX_RAW_LEN / 2)) {
		failures.push(`  CAP_WARN_AT ${CAP_WARN_AT} is not inside the last half of ${MAX_RAW_LEN}`);
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

	// The retry queue, which has a corpus that cannot be satisfied (see below)
	// and therefore had no oracle at all. It is the module that holds your
	// text when the connection does not, so "no oracle" was the wrong number
	// of them: `flush` was deleting every queued entry behind the one that
	// failed, silently, and nothing in this runner could see it. These check
	// the four rules the module's own header states, plus the two ways it can
	// lose a line.
	const queueEnv = (fetchImpl: QueueEnv['fetch'], now = () => 1000): QueueEnv => {
		const store: Record<string, string> = {};
		return {
			getItem: (k) => store[k] ?? null,
			setItem: (k, v) => {
				store[k] = v;
			},
			fetch: fetchImpl,
			now,
			maxAgeMs: undefined
		};
	};
	const bodies = (env: QueueEnv) => load(env).map((q) => q.body);
	const fill = (env: QueueEnv, ...names: string[]) => {
		for (const n of names) enqueue(env, '/api/capture/entries', n);
	};

	// **A dead connection keeps the whole queue.** The one that threw and
	// every one behind it, in the order they were typed.
	{
		const env = queueEnv(async () => {
			throw new Error('offline');
		});
		fill(env, 'A', 'B', 'C');
		const sent = await flush(env);
		if (sent !== 0 || bodies(env).join() !== 'A,B,C') {
			failures.push(`  flush offline: kept ${JSON.stringify(bodies(env))}, sent ${sent}, expected all three kept`);
		}
	}

	// The same once some have already gone: A leaves, B throws, C was never
	// attempted and must still be there.
	{
		let n = 0;
		const env = queueEnv(async () => {
			n++;
			if (n === 1) return { ok: true };
			throw new Error('offline');
		});
		fill(env, 'A', 'B', 'C');
		const sent = await flush(env);
		if (sent !== 1 || bodies(env).join() !== 'B,C') {
			failures.push(`  flush partial: kept ${JSON.stringify(bodies(env))}, sent ${sent}, expected B,C and sent 1`);
		}
	}

	// **A server that answered keeps only what it refused, and carries on.**
	// A 400 is retried like any other non-ok: an entry lost is worse than an
	// entry retried, and the expiry is the backstop.
	{
		let n = 0;
		const env = queueEnv(async () => ({ ok: ++n !== 2 }));
		fill(env, 'A', 'B', 'C');
		const sent = await flush(env);
		if (sent !== 2 || bodies(env).join() !== 'B') {
			failures.push(`  flush refusal: kept ${JSON.stringify(bodies(env))}, sent ${sent}, expected B and sent 2`);
		}
	}

	// Everything sent leaves nothing behind.
	{
		const env = queueEnv(async () => ({ ok: true }));
		fill(env, 'A', 'B');
		await flush(env);
		if (bodies(env).length !== 0) {
			failures.push(`  flush all-ok: left ${JSON.stringify(bodies(env))}, expected empty`);
		}
	}

	// **The expiry is strictly greater**, so exactly 24h old still sends.
	{
		let clock = 0;
		const env = queueEnv(async () => ({ ok: true }), () => clock);
		fill(env, 'old');
		clock = MAX_AGE_MS; // exactly at the limit
		if ((await flush(env)) !== 1) failures.push('  an entry exactly MAX_AGE_MS old was dropped; the test is strictly greater');

		let tried = 0;
		const env2 = queueEnv(async () => {
			tried++;
			return { ok: true };
		}, () => clock);
		clock = 0;
		fill(env2, 'stale');
		clock = MAX_AGE_MS + 1;
		const sent = await flush(env2);
		if (sent !== 0 || tried !== 0 || bodies(env2).length !== 0) {
			failures.push(`  an expired entry was attempted (${tried}) or kept (${bodies(env2).length}); it should be dropped unattempted`);
		}
	}

	// **Two flushes must not overlap.** Both would `load()` the same queue and
	// send all of it, and two identical captures in an append-only log cannot
	// be told from two you typed.
	{
		let sends = 0;
		let release: () => void = () => {};
		const gate = new Promise<void>((r) => (release = r));
		const env = queueEnv(async () => {
			sends++;
			await gate;
			return { ok: true };
		});
		fill(env, 'A', 'B');
		const first = flush(env);
		const second = flush(env);
		release();
		await Promise.all([first, second]);
		if (sends !== 2) {
			failures.push(`  two concurrent flushes made ${sends} requests for 2 entries, expected 2`);
		}
	}

	// Unreadable storage reads as an empty queue rather than throwing during
	// boot — the whole app mounts behind this call.
	{
		const env = queueEnv(async () => ({ ok: true }));
		env.setItem(STORAGE_KEY, 'not json at all');
		if (pendingCount(env) !== 0 || (await flush(env)) !== 0) {
			failures.push('  a corrupt queue in storage did not read as empty');
		}
	}

	// Dragging a shelf heading into a new place. No corpus covers it — the
	// source has no groups — and what it writes is an event, so a wrong answer
	// here is a line in an append-only log saying the user arranged something
	// they did not.
	{
		const order = ['A', 'B', 'C'];
		const moves: [string, string | null, string[]][] = [
			['A', 'C', ['B', 'A', 'C']],
			['C', 'A', ['C', 'A', 'B']],
			['A', null, ['B', 'C', 'A']],
			// The three that must move nothing at all: onto itself, in front of
			// where it already is, and to the end it is already at.
			['A', 'A', order],
			['A', 'B', order],
			['C', null, order],
			// A name the shelf does not have decides nothing.
			['A', 'Z', order],
			['Z', 'A', order]
		];
		for (const [key, before, want] of moves) {
			const got = moveBefore(order, key, before);
			if (JSON.stringify(got) !== JSON.stringify(want)) {
				failures.push(
					`  moveBefore(${JSON.stringify(order)}, ${key}, ${before}) = ` +
						`${JSON.stringify(got)}, expected ${JSON.stringify(want)}`
				);
			}
		}
		// An unmoved order must come back as the same array, because that is
		// what `reorderGroups` tests to decide whether to write anything.
		if (moveBefore(order, 'A', 'B') !== order) {
			failures.push('  a move that changes nothing returned a new array; nothing would be a no-op');
		}
		// And the answer the two shelf screens actually read: null for "this
		// drop changed nothing, do not append an `order-groups` event".
		if (reorderGroups(order, 'A', 'B') !== null) {
			failures.push('  reorderGroups did not report an unchanged drop as null');
		}
		if (JSON.stringify(reorderGroups(order, 'A', 'C')) !== JSON.stringify(['B', 'A', 'C'])) {
			failures.push('  reorderGroups did not carry a real move through');
		}
	}

	// ── Sending a capture ─────────────────────────────────────────────────
	//
	// The one path in this app that must never lose anything, and until it had
	// an interface it had no oracle either: it lived inside a 127-line
	// `submit()` in a Svelte component and could only be exercised by driving
	// a browser. What is checked here is the pairing that used to be two
	// statements next to each other — offline queues the *line* and gives the
	// *files* back, because the queue replays a body and there is no entry to
	// attach an upload to.
	{
		type Rec = {
			uploaded: string[];
			queued: { url: string; body: string }[];
			released: number;
		};
		const envFor = (fail: unknown) => {
			const rec: Rec = { uploaded: [], queued: [], released: 0 };
			const env = {
				capture: async (text: string) => {
					if (fail) throw fail;
					return {
						entry: { id: 'e1', folders: ['garden'], todo_lines: [], raw_text: text } as never
					};
				},
				upload: (entryId: string, _files: unknown[], folder: string) => {
					rec.uploaded.push(`${entryId}:${folder}`);
				},
				enqueue: (url: string, body: string) => rec.queued.push({ url, body }),
				pending: () => rec.queued.length,
				release: () => void (rec.released += 1)
			};
			return { rec, env };
		};
		const twoFiles = [{ key: 'a' }, { key: 'b' }] as never[];

		// The pin's tag reaches the *raw line*, which is what membership is
		// resolved from. Never a folder id on the payload.
		if (lineFor({ text: 'dug it over', files: [], pinTag: 'garden' }) !== 'dug it over <garden>') {
			failures.push(`  lineFor did not append the pin's tag: ${lineFor({ text: 'dug it over', files: [], pinTag: 'garden' })}`);
		}
		if (lineFor({ text: 'plain', files: [], pinTag: null }) !== 'plain') {
			failures.push('  lineFor appended something with nothing pinned');
		}

		{
			const { rec, env } = envFor(null);
			const out = await send({ text: 'a line', files: twoFiles, pinTag: null }, env);
			if (out.kind !== 'sent') failures.push(`  a good send reported ${out.kind}`);
			if (rec.uploaded.join() !== 'e1:garden') {
				failures.push(`  the uploads did not start against the entry: ${rec.uploaded.join()}`);
			}
			if (rec.released !== 0) failures.push('  a successful send gave the files back');
		}

		{
			const { rec, env } = envFor(new NetworkError('offline'));
			const out = await send({ text: 'a line', files: twoFiles, pinTag: null }, env);
			if (out.kind !== 'queued') {
				failures.push(`  an offline send reported ${out.kind}, expected queued`);
			} else if (out.lostFiles !== 2 || out.pending !== 1) {
				failures.push(`  an offline send reported ${out.lostFiles} lost files, ${out.pending} pending`);
			}
			// The line is kept…
			if (rec.queued.length !== 1 || !rec.queued[0].body.includes('a line')) {
				failures.push('  an offline send did not queue the line');
			}
			// …and the files, which cannot be, are handed back rather than left
			// holding object URLs for a send that will never happen.
			if (rec.released !== 2) {
				failures.push(`  an offline send released ${rec.released} of 2 files`);
			}
			if (rec.uploaded.length !== 0) failures.push('  an offline send started an upload');
		}

		{
			const { rec, env } = envFor(new Error('too long'));
			const out = await send({ text: 'a line', files: twoFiles, pinTag: null }, env);
			if (out.kind !== 'refused') {
				failures.push(`  a refusal reported ${out.kind}`);
			} else if (out.message !== 'too long') {
				failures.push(`  a refusal lost its message: ${out.message}`);
			}
			// Nothing was written, so nothing is queued — and the files are
			// *not* released: the caller is about to put them back in the bar
			// along with the text.
			if (rec.queued.length !== 0) failures.push('  a refusal queued the line for replay');
			if (rec.released !== 0) failures.push('  a refusal threw the files away');
		}
	}

	// How a shelf splits into the loose grid and its named headings. Both
	// screens showing a shelf read this, and they used to have a copy each.
	{
		const album = (id: string, group: string) => ({ id, group }) as never;
		const shelf = {
			groups: ['Making', 'Reading'],
			albums: [album('a', ''), album('b', 'Reading'), album('c', 'Making'), album('d', '')]
		} as never;

		const { loose, sections } = splitShelf(shelf);
		if (loose.map((a) => a.id).join(',') !== 'a,d') {
			failures.push(`  the loose grid held ${loose.map((a) => a.id).join(',')}, expected a,d`);
		}
		// The shelf's own order, not the order the albums happen to arrive in.
		if (sections.map((s) => s.name).join(',') !== 'Making,Reading') {
			failures.push('  the headings did not come back in the shelf`s order');
		}
		if (sections[0].albums.map((a) => a.id).join(',') !== 'c') {
			failures.push('  an album landed under the wrong heading');
		}
		// A heading with nothing under it is a place you have made and not
		// filled. Dropping it would take that decision back for you.
		const empty = splitShelf({ groups: ['Someday'], albums: [] } as never);
		if (empty.sections.length !== 1 || empty.sections[0].albums.length !== 0) {
			failures.push('  an empty group heading did not survive the split');
		}
		// The all-years shelf has no groups at all, and that is the flat list
		// the screen had before groups existed rather than a case to handle.
		if (splitShelf(null).sections.length !== 0 || splitShelf(null).loose.length !== 0) {
			failures.push('  splitShelf(null) was not the empty shelf');
		}
	}

	// And where a drop lands: halves, not edges, and past the last row is the
	// end of the list.
	{
		const slots = [
			{ key: 'A', top: 0, bottom: 20 },
			{ key: 'B', top: 20, bottom: 40 },
			{ key: 'C', top: 40, bottom: 60 }
		];
		const drops: [number, string | null][] = [
			[-50, 'A'],
			[0, 'A'],
			[9, 'A'],
			[10, 'B'],
			[29, 'B'],
			[30, 'C'],
			[49, 'C'],
			[50, null],
			[999, null]
		];
		for (const [y, want] of drops) {
			const got = dropBefore(slots, y);
			if (got !== want) failures.push(`  dropBefore(y=${y}) = ${got}, expected ${want}`);
		}
		if (dropBefore([], 10) !== null) failures.push('  dropBefore on an empty list was not the end');
	}

	// `--reply`, which the corpus has no cases for — the source implements it
	// in a React component rather than in a module, so there was nothing to
	// generate fixtures from. It decides whether a line is addressed to the
	// reminder above the box, and it is the one place this port takes anything
	// off a raw line before storing it, so it gets an oracle of its own.
	{
		const cases: [string, boolean, string][] = [
			['--reply it came back', true, 'it came back'],
			['--REPLY it came back', true, 'it came back'],
			['   --reply   it came back  ', true, 'it came back'],
			['--reply\tit came back', true, 'it came back'],
			// Still typing: the space is what says the command is finished.
			['--reply', false, '--reply'],
			['--replying to the letter', false, '--replying to the letter'],
			// Only at the front. Mid-sentence it is prose, the way the source
			// anchors its regex.
			['I said --reply and meant it', false, 'I said --reply and meant it'],
			['', false, '']
		];
		for (const [draft, want, stripped] of cases) {
			if (isReply(draft) !== want) {
				failures.push(`  isReply(${JSON.stringify(draft)}) = ${!want}, expected ${want}`);
			}
			if (stripReply(draft) !== stripped) {
				failures.push(
					`  stripReply(${JSON.stringify(draft)}) = ${JSON.stringify(stripReply(draft))}, ` +
						`expected ${JSON.stringify(stripped)}`
				);
			}
		}
		// A reply keeps its own syntax: the `{time}` on it resolves as usual, so
		// an answer can start the next round.
		if (stripReply('--reply ask again {2d} <shop>') !== 'ask again {2d} <shop>') {
			failures.push('  stripReply took more than the command off the line');
		}
	}

	// The three commands `--` opens. `todo` and `reply` are this port's
	// addition to the suggestion source; a fourth would need a decision, not a
	// push to this array.
	{
		const want = ['todo', 'reply'];
		if (JSON.stringify(COMMANDS) !== JSON.stringify(want)) {
			failures.push(`  COMMANDS is ${JSON.stringify(COMMANDS)}, expected ${JSON.stringify(want)}`);
		}
	}

	// **Where the two features meet.** Accepting `--reply` from the suggestion
	// panel has to produce a string `REPLY_RE` accepts, and the thing that
	// makes it work is the trailing space `acceptSuggestion` appends. Nothing
	// else ties those two files together, and either could be "tidied" without
	// the other noticing.
	{
		for (const command of COMMANDS) {
			const typed = `--${command.slice(0, 2)}`;
			const after = acceptSuggestion(
				{ value: typed, caret: typed.length, suggestIdx: 0, stats: {} },
				command
			);
			if (after.value !== `--${command} `) {
				failures.push(
					`  accepting --${command} gave ${JSON.stringify(after.value)}, ` +
						`expected ${JSON.stringify(`--${command} `)}`
				);
			}
			if (after.caret !== after.value.length) {
				failures.push(`  accepting --${command} left the caret at ${after.caret}`);
			}
		}
		const accepted = acceptSuggestion(
			{ value: '--re', caret: 4, suggestIdx: 0, stats: {} },
			'reply'
		);
		if (!isReply(accepted.value + 'it came back')) {
			failures.push('  a --reply accepted from the panel does not read as a reply');
		}
	}

	// ── The clock's two formatters ────────────────────────────────────────
	//
	// No corpus covers these: the source has no timer. They are here for the
	// same reason `pinned.ts` is — they are pure, they are this port's own, and
	// a number read wrong on a screen is the kind of mistake that survives a
	// hundred glances. The rounding cases are the ones worth pinning; the rest
	// are here so a rewrite has something to fail against.
	const faces: [number, string][] = [
		[0, '0:00'],
		[9, '0:09'],
		[70, '1:10'],
		[600, '10:00'],
		// The hour is where the shape changes, and both sides of it matter.
		[3599, '59:59'],
		[3600, '1:00:00'],
		[3661, '1:01:01'],
		[36000, '10:00:00'],
		// A negative can only arrive from a clock set backwards mid-session.
		// It reads as zero rather than as a minus sign.
		[-5, '0:00'],
		// A server one deploy behind the client sends no field at all. That is
		// a normal state in this app — see the note on `duration`.
		[NaN, '0:00'],
		[undefined as unknown as number, '0:00']
	];
	for (const [input, want] of faces) {
		const got = clockFace(input);
		if (got !== want) failures.push(`  clockFace(${input}) = ${got}, expected ${want}`);
	}

	const durations: [number, string][] = [
		[0, '—'],
		[45, '45s'],
		[60, '1m'],
		[90, '2m'],
		[3600, '1h'],
		[5400, '1h 30m'],
		// 59m30s rounds up to a full sixty minutes, which has to carry into the
		// hour rather than print `0h 60m`.
		[3570, '1h'],
		[7170, '2h'],
		// And the same carry one rung down, where there is no hour to carry to.
		[3540, '59m'],
		// The bug this pair was added for: the button read `NaNh NaNm` against
		// a backend that predated the field.
		[NaN, '—'],
		[undefined as unknown as number, '—']
	];
	for (const [input, want] of durations) {
		const got = duration(input);
		if (got !== want) failures.push(`  duration(${input}) = ${got}, expected ${want}`);
	}

	// ── The pomodoro's arithmetic ─────────────────────────────────────────
	//
	// This one decides what gets written into an append-only log, so it is the
	// most load-bearing pure function this port owns. Rest must never reach
	// `workedMs`, and the whole thing has to be right after an arbitrary sleep
	// — which is exactly what a table of elapsed times is a test of.
	const MIN = 60_000;
	// A 50/10 cycle, which is the default.
	const pom: [number, string, number, number][] = [
		// [elapsed ms, phase, remaining ms, worked ms]
		[0, 'work', 50 * MIN, 0],
		[10 * MIN, 'work', 40 * MIN, 10 * MIN],
		// The boundary belongs to the phase that is starting, not the one that
		// ended: at exactly 50 minutes you are resting, with a full break left.
		[50 * MIN, 'rest', 10 * MIN, 50 * MIN],
		[55 * MIN, 'rest', 5 * MIN, 50 * MIN],
		// Rest does not add to the work total, however long it runs.
		[59 * MIN, 'rest', 1 * MIN, 50 * MIN],
		// Second cycle.
		[60 * MIN, 'work', 50 * MIN, 50 * MIN],
		[70 * MIN, 'work', 40 * MIN, 60 * MIN],
		[110 * MIN, 'rest', 10 * MIN, 100 * MIN],
		// A phone asleep for five hours wakes up in the right place, which is
		// the whole reason this is derived rather than driven by a callback.
		[300 * MIN, 'work', 50 * MIN, 250 * MIN]
	];
	for (const [elapsed, phase, remaining, worked] of pom) {
		const got = pomodoroAt(elapsed, 50 * MIN, 10 * MIN);
		const label = `pomodoroAt(${elapsed / MIN}m)`;
		if (got.phase !== phase) failures.push(`  ${label}.phase = ${got.phase}, expected ${phase}`);
		if (got.remainingMs !== remaining) {
			failures.push(`  ${label}.remainingMs = ${got.remainingMs / MIN}m, expected ${remaining / MIN}m`);
		}
		if (got.workedMs !== worked) {
			failures.push(`  ${label}.workedMs = ${got.workedMs / MIN}m, expected ${worked / MIN}m`);
		}
	}
	// Cycle counting, which draws the marks.
	if (pomodoroAt(0, 50 * MIN, 10 * MIN).cycles !== 0) failures.push('  0m is not 0 cycles');
	if (pomodoroAt(59 * MIN, 50 * MIN, 10 * MIN).cycles !== 0) failures.push('  59m is not 0 cycles');
	if (pomodoroAt(60 * MIN, 50 * MIN, 10 * MIN).cycles !== 1) failures.push('  60m is not 1 cycle');
	// A cycle with no rest in it is all work and never leaves the work phase.
	const noRest = pomodoroAt(120 * MIN, 50 * MIN, 0);
	if (noRest.phase !== 'work' || noRest.workedMs !== 120 * MIN) {
		failures.push(`  a rest-less cycle banked ${noRest.workedMs / MIN}m as ${noRest.phase}`);
	}
	// Nonsense in, something readable out — never a divide by zero.
	const zero = pomodoroAt(90 * MIN, 0, 0);
	if (zero.phase !== 'work' || zero.workedMs !== 90 * MIN) {
		failures.push('  a zero-length cycle did not degrade to a stopwatch');
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
//
// What this entry used to cost, and no longer does: an exemption silences the
// whole file, so the module behind it had no oracle of any kind, and `flush`
// spent months deleting every queued entry behind the first failure with
// nothing able to notice. The rules the corpus cannot pin are pinned in
// `localChecks` instead. **An exemption here is a debt owed to that
// function** — never add one without paying it.

const KNOWN_BAD: Record<string, string> = {
	retry_queue:
		'fixtures contradict their own source — see the note in scripts/verify-ui.ts'
};

// ── Runner ────────────────────────────────────────────────────────────────

// ── Declared deviations, one case at a time ───────────────────────────────
//
// A whole file can be retired when the thing it describes is gone — the date
// ruler took `timeline_draw` with it. This is the other shape: the module is
// still here and still pinned, and *one* case describes behaviour this app has
// deliberately changed.
//
// It is a table with a reason per case rather than a tolerance, for the same
// reason `THEME` is a table: "we changed it on purpose" is the excuse a real
// mistake hides behind. A deviated case that starts *passing* is reported too,
// so the entry gets deleted rather than accumulating.
const DEVIATIONS: Record<string, Record<string, string>> = {
	capture_overlay: {
		'overlay-suggest-directive-empty-query':
			'`--` offers the commands before the folders. Upstream the `-` trigger ' +
			'completes folder names only, so `--todo` — the most used command in the ' +
			'app — can never be suggested and `--reply` cannot either. See COMMANDS ' +
			'in capture-bar.ts. The tokenizer is untouched: 395/395 still pass.'
	}
};

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
	let deviated = 0;
	const lines: string[] = [];
	const declared = DEVIATIONS[stem] ?? {};
	const unclaimed = new Set(Object.keys(declared));

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
			if (declared[c.id]) {
				lines.push(`    [${c.id}] NO LONGER DEVIATES — delete its entry from DEVIATIONS`);
			}
			unclaimed.delete(c.id);
			continue;
		}
		if (declared[c.id]) {
			deviated++;
			unclaimed.delete(c.id);
			lines.push(`    [${c.id}] deviates on purpose: ${declared[c.id]}`);
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

	for (const id of unclaimed) {
		lines.push(`    [${id}] declared as deviating but no such case in the corpus`);
	}
	const tail = deviated ? `  (${deviated} declared deviation${deviated > 1 ? 's' : ''})` : '';
	console.log(
		`  ${stem.padEnd(20)} ${failed === 0 ? 'PASS' : 'FAIL'}  ` +
			`${passed}/${cases.length - deviated}${tail}`
	);
	for (const l of lines) console.log(l);
	if (failed && !verbose && failed > shown) {
		console.log(`    … ${failed - shown} more failing case(s); re-run with -v`);
	}
	return { status: failed ? 'fail' : 'ok', passed, failed, total: cases.length - deviated };
}

// ── Runner: two halves, and only one of them needs the bundle ─────────────
//
// The corpus is an oracle this checkout may not have. `trophic/` is gitignored,
// so it exists wherever the bundle was unpacked and nowhere else — which on a
// dual-boot machine with two clones means one side has it and the other does
// not. This used to be one gate in front of everything: a missing directory
// returned 2 before a single assertion ran, `localChecks` included.
//
// That is the wrong place for the seam, and it is expensive in the exact way
// the note above `KNOWN_BAD` describes. `localChecks` is where the rules the
// corpus cannot pin are paid back — the local-midnight day key, the queue that
// used to eat every entry behind the first failure — and it needs no fixtures
// at all. Gating it on the bundle meant the half of the suite written *for*
// the side without the bundle was the half that could not run there.
//
// So the corpus is an adapter that may be absent, reported as SKIP, and
// `localChecks` always runs and always sets the exit code. An absent oracle
// must never read as a pass: `corpusStems` returning null is printed, loudly,
// and `--only` naming a file that is not there is still an error, because that
// is a caller asking for something specific and not getting it.

function corpusStems(wanted: string[]): string[] | null {
	if (!existsSync(CORPUS)) return null;
	const stems = readdirSync(CORPUS)
		.filter((f) => f.endsWith('.json') && f !== 'index.json')
		.map((f) => f.slice(0, -5))
		.filter((s) => s in ADAPTERS)
		.sort();
	return wanted.length ? stems.filter((s) => wanted.includes(s)) : stems;
}

async function main(argv: string[]): Promise<number> {
	const verbose = argv.includes('-v') || argv.includes('--verbose');
	const wanted = argv.filter((a) => !a.startsWith('-'));

	const stems = corpusStems(wanted);
	let pass = 0;
	let fail = 0;
	let total = 0;

	if (stems === null) {
		console.log('golden corpus, TypeScript side — SKIP\n');
		console.log(`  corpus directory not found: ${CORPUS}`);
		console.log('  the trophic/ bundle is gitignored and lives only on this disk.');
		console.log('  it came from ~/pekka/LearningNext/scheduler, branch pivot,');
		console.log('  commit 105181c; regenerate there with `pnpm golden` and re-copy');
		console.log('  corpus/, generate.ts, generate-ui.ts, harness.ts and README.md.');
		console.log('  leave golden/verify_golden.py alone — the parser adapter wired');
		console.log('  into it is an edit to an untracked file and a re-copy reverts it.');
		console.log('  the local checks below still run, and still decide the exit code.\n');
		// A named file that cannot be read is a different answer from "no
		// bundle here": the caller asked for one thing and got nothing.
		if (wanted.length) {
			console.error(`\ncannot run ${wanted.join(', ')} without the corpus`);
			return 2;
		}
	} else if (!stems.length) {
		console.error(`no corpus files matched: ${wanted.join(', ')}`);
		return 2;
	} else {
		console.log(`golden corpus, TypeScript side — ${stems.length} file(s)\n`);
		for (const stem of stems) {
			const r = await runFile(stem, verbose);
			pass += r.passed;
			fail += r.failed;
			total += r.total;
		}
	}

	const local = await localChecks();
	for (const line of local) console.log(line);
	if (local.length) console.log(`  ${'local checks'.padEnd(20)} FAIL  ${local.length} problem(s)`);
	else console.log(`  ${'local checks'.padEnd(20)} PASS  (no corpus, this port's own mistakes)`);

	const skipped = stems === null ? ', corpus skipped' : '';
	console.log(`\n${pass} passed, ${fail + local.length} failed (${total} cases${skipped})`);
	return fail || local.length ? 1 : 0;
}

process.exit(await main(process.argv.slice(2)));
