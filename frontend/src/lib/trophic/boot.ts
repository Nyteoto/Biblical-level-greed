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

export type BootLine = { part: string; state: string };

function pick<T>(from: T[], rng: () => number): T {
	return from[Math.floor(rng() * from.length)];
}

/** A shuffled run of lines, media mixed in wherever the log gave us any. */
export function bootLines(media: string[], count: number, rng: () => number = Math.random): BootLine[] {
	// Media first in the pool but not first on screen: the shuffle is what puts
	// a photograph between two modules, which is what makes it read as one
	// system rather than two lists.
	const pool = [...PARTS, ...media.map((ref) => ref.split('/').pop() ?? ref)];
	const out: BootLine[] = [];
	const seen = new Set<string>();
	while (out.length < count && seen.size < pool.length) {
		const part = pick(pool, rng);
		if (seen.has(part)) continue;
		seen.add(part);
		out.push({ part, state: pick(STATES, rng) });
	}
	return out;
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
