/**
 * What the boot screen reads out, and how it decides.
 *
 * The screen is theatre — nothing is loading, the shell is static files off
 * localhost — but the names it scrolls are real, which is the difference
 * between a machine introducing itself and a progress bar telling a lie. Every
 * line here is a file this app actually has, and the media names are the user's
 * own, read from the log.
 *
 * Filenames only. `CLAUDE.md` is explicit that listing them is fine and opening
 * them is not, and nothing here opens anything.
 *
 * Everything is shuffled per boot, so two launches never read the same. That is
 * the whole reason the pool is long: a fixed list read in order stops being a
 * machine waking up and becomes a screen you have already read.
 */

/** Real modules, backend and front. Kept honest — anything deleted from the
 *  repo must leave this list too, or the boot screen starts naming ghosts. */
const PARTS = [
	'eventlog.py',
	'index.py',
	'state.py',
	'parser.py',
	'reminder.py',
	'timeutil.py',
	'conditions.py',
	'foundation.py',
	'watcher.py',
	'storage.py',
	'import_csv.py',
	'colors.py',
	'tokenize.ts',
	'colorize.ts',
	'trie.ts',
	'richtext.ts',
	'longpress.ts',
	'holdable.ts',
	'portal.ts',
	'retry-queue.ts',
	'validation.ts',
	'monitor.svelte.ts',
	'pinned.svelte.ts',
	'uploads.svelte.ts',
	'data/log/*.jsonl',
	'data/capture/log',
	'index.sqlite',
	'data/seed'
];

/** What a line reports. None of it is a health check and none of it pretends
 *  to be — these are the verbs this codebase actually uses about itself. */
const STATES = ['ok', 'read', 'folded', 'replayed', 'derived', 'mounted', 'cached', 'warm'];

/**
 * One true thing about the app, shown above the wordmark while it boots.
 *
 * Sourced from the Manual and from the rules this codebase actually keeps, not
 * written fresh — a hint that drifts from the app is worse than no hint, and
 * the Manual is the thing that gets corrected when behaviour changes. Kept to
 * one line each, because it is read in passing.
 */
const HINTS = [
	'a tag is real the moment you type it — nothing has to exist first',
	'`<pointer>` is the only syntax that can put a line in a folder',
	'`@helsinki` marks where you were; `a@b.com` stays plain text',
	'`\\win` and `\\stuck` are counted and drawn, and never interpreted',
	'`{2d}` is worked out from the day you wrote it, so a rebuild reproduces it',
	'`--todo` makes a line tickable; the directive itself is not kept',
	'hold a folder card for its name, its tags, its state',
	'hold a photograph to make it a folder’s face',
	'holding anywhere draws a ring — that is the app asking what you meant',
	'mapping a tag is retroactive: every line ever written with it joins',
	'nothing is edited or deleted — a mistake is corrected by appending its undo',
	'the log is the truth; every screen here is a fold over it',
	'delete the index whenever you like — it is rebuilt from the log',
	'the Log tab flips between the year shelf and what you were reading',
	'one hue, and one exception: a refusal is the only other colour',
	'the monitor is a layer — every part of it is a dial in Settings'
];

export function bootHint(rng: () => number = Math.random): string {
	return HINTS[Math.floor(rng() * HINTS.length)];
}

export type BootLine = { id: number; part: string; state: string };

let seq = 0;

function pick<T>(from: T[], rng: () => number): T {
	return from[Math.floor(rng() * from.length)];
}

/** Everything a boot can name: this repo's parts, plus the user's own media. */
export function bootPool(media: string[]): string[] {
	// Media mixed into the same pool rather than kept as its own group: the
	// shuffle is what puts a photograph between two modules, which is what makes
	// it read as one system waking up rather than two lists.
	return [...PARTS, ...media.map((ref) => ref.split('/').pop() ?? ref)];
}

/** One more line for the roll. Carries an id because the list scrolls and the
 *  same name may legitimately come round twice in a long boot. */
export function bootLine(pool: string[], rng: () => number = Math.random): BootLine {
	return { id: ++seq, part: pick(pool, rng), state: pick(STATES, rng) };
}

/**
 * Where the bar is at a given moment, as a fraction.
 *
 * Segments, not a ramp. A bar that fills at a constant rate is a bar measuring
 * a clock, and everyone reads it as one; real work arrives in lumps, stalls,
 * and finishes in a rush. The stalls are the point — they are what make the
 * lumps look like something completing.
 *
 * Built once per boot as a list of stops so the bar and the clock cannot
 * disagree: whatever the segments do in between, the last one is 1 at the end.
 */
export function bootSegments(rng: () => number = Math.random): number[] {
	const count = 4 + Math.floor(rng() * 3); // four to six lumps
	const stops: number[] = [];
	let at = 0;
	for (let i = 0; i < count - 1; i++) {
		at += (1 - at) * (0.25 + rng() * 0.4);
		stops.push(Math.min(0.93, at));
	}
	stops.push(1);
	return stops;
}
