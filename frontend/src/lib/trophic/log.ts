/**
 * How the album screen decides what a day looks like.
 *
 * Split out of the component for the reason the rest of this port's behaviour
 * is: **anything that decides what a screen shows belongs in a module the
 * corpus (or a local check) can replay; the component keeps the DOM, the
 * timers and the measuring.** None of the corpus's fixtures describe this
 * screen — it is this port's own invention — so `verify-ui.ts`'s local checks
 * are the oracle, and they exist because the bugs this file can have are
 * exactly the kind that hide: they swallow days rather than crashing.
 *
 * **A day is a page and every page is dressed the same.** There used to be two
 * shapes here — a lead day with the photograph and the caption, and a light
 * row with a date and a line — plus a fold that merged runs of quiet days into
 * one strip. All three existed because three hundred days shared one scroll
 * and only the top of it could afford anything. A deck removed that constraint
 * and took the three shapes with it: see `paginate` below, and `PageDeck` for
 * why turning pages is not the one-day-at-a-time travel this screen refuses.
 */

import type { Entry } from './api';

export type Day = {
	key: string;
	entries: Entry[];
	/** Every attachment written on this day, in the order the entries were. */
	media: { ref: string; entry: Entry }[];
	/** Entries that said something. A capture with nothing but a photograph in
	 *  it is a real capture, and it is drawn by the grid rather than the list. */
	lines: Entry[];
};

/** Newest first, like the log reads. */
export function groupDays(entries: Entry[]): Day[] {
	const byDay = new Map<string, Entry[]>();
	for (const entry of entries) {
		if (!byDay.has(entry.day)) byDay.set(entry.day, []);
		byDay.get(entry.day)!.push(entry);
	}
	return [...byDay.entries()]
		.sort((a, b) => b[0].localeCompare(a[0]))
		.map(([key, list]) => ({
			key,
			entries: list,
			media: list.flatMap((entry) => (entry.media ?? []).map((ref) => ({ ref, entry }))),
			lines: list.filter((entry) => entry.clean_text.trim().length > 0)
		}));
}

// ── Pages ─────────────────────────────────────────────────────────────────
//
// The reading view is a deck of pages and a page is a day. This is the whole
// of the rule that decides what is on one, and it is here rather than in the
// component for the reason the rest of this file is: a page that silently
// drops a line is the kind of bug that hides, and a pure function is a thing
// `verify-ui.ts` can hold to never dropping one.
//
// **Pages are for reading; the instruments are still for travelling.** The
// year rail, the month spine, the chapter list and the jump field all land on
// a page directly, so no day is ever more than one gesture away and turning is
// only ever the adjacent-day move. That is the rule the album screen has
// always had, restated for a view that turns instead of scrolling.

/** One page: a day, or one part of a day too heavy to sit on a single one. */
export type Shot = Day['media'][number];

export type Page = {
	/** `2026-08-14#0` — unique within a deck, and stable across a redraw,
	 *  which is what both `{#key}` and the `{#each}` key need. */
	key: string;
	day: Day;
	/** 0-based. Almost every day is one page and this is 0. */
	part: number;
	parts: number;
	/** The lead photograph and the line written beside it. **The first part
	 *  only** — a day is recognised once, and a continuation that opened with
	 *  the same plate again would read as the day starting over. */
	hero: Shot | null;
	caption: Entry | null;
	/** The day's other attachments, for the ribbon. First part only. */
	ribbon: Shot[];
	/** The day's whole pool, on every part, so a lightbox opened from page 3
	 *  still walks the day rather than the page. */
	shots: Shot[];
	/** The lines this part draws, newest first. */
	lines: Entry[];
};

/** How many lines a page holds before the day continues onto another. A
 *  tuned constant, not a measurement: measuring rendered height means a
 *  layout pass per keystroke of reflow, and a deterministic page is one a
 *  local check can hold. A page that runs a little long simply scrolls —
 *  scrolling *inside* a page is reading, which was never the thing the album
 *  screen refused. */
const PAGE_LINES = 7;
/** The first part of a day holds fewer, because it is also carrying a
 *  250px photograph and a ribbon under it. */
const PAGE_LINES_LEAD = 4;
/** A line this long is several on screen once it wraps, so it costs two. */
const LONG_LINE = 400;

function lineCost(entry: Entry): number {
	return entry.clean_text.length > LONG_LINE ? 2 : 1;
}

/**
 * A day's pages, in reading order.
 *
 * Everything a page draws is decided here rather than in the component, so
 * that "which entries get drawn" is answered exactly once. `LeadDay` used to
 * work this out for itself — the hero, the caption promoted out of the list,
 * the silent replies merged back in — and a second copy of that reckoning in
 * a paged view is a second chance to lose a line.
 */
function pagesOf(day: Day): Page[] {
	// A reply's attachments belong in its own bubble and are never the day's
	// hero. Same rule `LeadDay` had, and the reason it had it: promoting one
	// made the reply into a caption, which is the one shape that says this is
	// not part of a conversation.
	const shots = day.media.filter((shot) => !shot.entry.reply_to);
	const hero = shots[0] ?? null;
	const caption = hero?.entry ?? null;
	const ribbon = shots.slice(1);

	const rest = day.lines.filter((entry) => entry.id !== caption?.id);
	/** A reply that said nothing — a photograph and no words. `day.lines`
	 *  keeps only entries that said something, so without this one would be
	 *  stored, threaded, and drawn nowhere at all. */
	const silent = day.entries.filter((entry) => entry.reply_to && !entry.clean_text.trim());
	const spoken = [...rest, ...silent].sort((a, b) => b.ts.localeCompare(a.ts));

	const chunks: Entry[][] = [];
	let current: Entry[] = [];
	let spent = 0;
	for (const entry of spoken) {
		const cap = chunks.length === 0 && hero ? PAGE_LINES_LEAD : PAGE_LINES;
		const price = lineCost(entry);
		// `current.length > 0` is what stops a single over-budget line looping
		// on an empty page forever: it always gets one of its own.
		if (current.length > 0 && spent + price > cap) {
			chunks.push(current);
			current = [];
			spent = 0;
		}
		current.push(entry);
		spent += price;
	}
	if (current.length > 0) chunks.push(current);
	// A day of nothing but a photograph is still a page.
	if (chunks.length === 0) chunks.push([]);

	return chunks.map((lines, part) => ({
		key: `${day.key}#${part}`,
		day,
		part,
		parts: chunks.length,
		hero: part === 0 ? hero : null,
		caption: part === 0 ? caption : null,
		ribbon: part === 0 ? ribbon : [],
		shots,
		lines
	}));
}

/**
 * How the album is cut: the whole year, one month, or one chapter.
 *
 * A month is a filter and not a rung, and so is a chapter — one view, cut
 * different ways. Which is why this is a value the deck takes rather than a
 * second screen, and why `scopeName` on the lens is the only thing left that
 * knows what to *call* a cut.
 */
export type DeckScope =
	| { kind: 'year' }
	| { kind: 'month'; month: string }
	| { kind: 'chapter'; first_month: number; last_month: number };

export const WHOLE_YEAR: DeckScope = { kind: 'year' };

/** A day key's month, 1-based. One reading of `YYYY-MM-DD`, because there
 *  were three: this one, `here + 1` in the month band, and `live` on Map. */
export const monthOf = (key: string) => Number(key.slice(5, 7));

/**
 * The days a scope leaves standing.
 *
 * This lived on the reading lens, upstream of `paginate` — which meant the
 * one check that matters here, that no line is drawn on no page at all, began
 * one function *after* the place days could go missing. A day dropped by a
 * filter the verifier could not see is exactly the silent failure `paginate`
 * was moved out of a component to prevent, so the filter moved out too.
 *
 * The lens still reads it directly for the contact sheet: one implementation,
 * two callers, and the deck and the sheet cannot disagree about what is in
 * scope.
 */
export function inScope(days: Day[], scope: DeckScope): Day[] {
	if (scope.kind === 'month') {
		return days.filter((d) => d.key.slice(0, 7) === scope.month);
	}
	if (scope.kind === 'chapter') {
		return days.filter((d) => {
			const month = monthOf(d.key);
			return month >= scope.first_month && month <= scope.last_month;
		});
	}
	return days;
}

/** The deck, newest page first — `days` is already in that order. */
export function paginate(days: Day[], scope: DeckScope = WHOLE_YEAR): Page[] {
	return inScope(days, scope).flatMap(pagesOf);
}

/**
 * How many sheet edges to draw behind the live page.
 *
 * The deck is a pile and the pile is not decoration: what stands behind the
 * page is what is left to read, so the stack thins as you go and thickens as
 * you come back. `cap` is only where it stops being countable by eye — a
 * hundred sheets and four sheets say the same thing at a glance, and the
 * `n of m` counter is what says the rest.
 *
 * Here rather than in the component because both ends are off-by-one traps
 * that look right: the last page must show no pile at all (there is nothing
 * under it), and an empty deck must not show one either.
 */
export function stackBehind(total: number, at: number, cap: number): number {
	if (total <= 0 || cap <= 0) return 0;
	const here = Math.min(Math.max(at, 0), total - 1);
	return Math.min(cap, total - here - 1);
}

/** Where `key` sits in the deck, or the nearest page at or before it — which
 *  is what "open me at this day" means when the day itself has nothing in it
 *  and so is not a page at all. `-1` when the deck holds nothing older. */
export function pageAt(pages: Page[], dayKey: string): number {
	const exact = pages.findIndex((p) => p.day.key === dayKey);
	if (exact >= 0) return exact;
	// Newest first, so the first page not newer than the target is the one
	// the reader meant.
	return pages.findIndex((p) => p.day.key <= dayKey);
}

/** Which page holds an entry, or -1. What `?entry=` lands on. */
export function pageOfEntry(pages: Page[], entryId: string): number {
	return pages.findIndex(
		(p) => p.lines.some((e) => e.id === entryId) || p.caption?.id === entryId
	);
}

/** `Sat 15 Aug`. A page's headline, and the date on the edges that turn it. */
export function dayLabel(key: string): string {
	const [y, m, d] = key.split('-').map(Number);
	return new Date(y, m - 1, d).toLocaleDateString(undefined, {
		weekday: 'short',
		day: 'numeric',
		month: 'short'
	});
}

/**
 * The ISO-8601 week number, which is the one the header means by `week 33`.
 *
 * Worth having the real algorithm rather than "day of year over seven": ISO
 * weeks start on Monday and belong to the year that holds their Thursday, so
 * the 1st of January is often week 52 or 53 of the year before. Getting that
 * wrong is invisible for eleven months and then wrong at exactly the moment a
 * year rolls over, which is the moment this app draws attention to.
 */
export function isoWeek(key: string): number {
	const [y, m, d] = key.split('-').map(Number);
	const date = new Date(Date.UTC(y, m - 1, d));
	// Move to the Thursday of this week; its year is the week-numbering year.
	const dow = (date.getUTCDay() + 6) % 7; // Monday = 0
	date.setUTCDate(date.getUTCDate() - dow + 3);
	const firstThursday = new Date(Date.UTC(date.getUTCFullYear(), 0, 4));
	const firstDow = (firstThursday.getUTCDay() + 6) % 7;
	firstThursday.setUTCDate(firstThursday.getUTCDate() - firstDow + 3);
	return 1 + Math.round((date.getTime() - firstThursday.getTime()) / (7 * 86400000));
}

/**
 * Which week of *this album* a day falls in, counting from 0.
 *
 * The header used to print `isoWeek`, which is the week of the calendar year —
 * `week 34` in August, a number that says where the planet is rather than where
 * the project is. Inside an album the only week worth counting is the album's
 * own, so the first week of anything is week 0 and it ticks over on Mondays
 * from there.
 *
 * Monday boundaries rather than rolling seven-day spans from the first entry:
 * a week is a thing with edges everyone already shares, and a project whose
 * weeks turn over on a Wednesday because that is when it started is a project
 * you have to do arithmetic about. `isoWeek` stays as it is — it is checked by
 * `verify-ui.ts` and it is still the right answer to a different question.
 */
export function albumWeek(first: string, key: string): number {
	return Math.round((mondayOf(key) - mondayOf(first)) / (7 * 86400000));
}

/** Midnight UTC on the Monday of `key`'s week. */
function mondayOf(key: string): number {
	const [y, m, d] = key.split('-').map(Number);
	const date = new Date(Date.UTC(y, m - 1, d));
	const dow = (date.getUTCDay() + 6) % 7; // Monday = 0
	date.setUTCDate(date.getUTCDate() - dow);
	return date.getTime();
}

/** `AUGUST 2026`, upper-cased by the type rather than here so the string stays
 *  readable in a tooltip. */
export function monthLabel(key: string): string {
	const [y, m] = key.split('-').map(Number);
	return new Date(y, m - 1, 1).toLocaleDateString(undefined, {
		month: 'long',
		year: 'numeric'
	});
}

export const MONTH_ABBR = [
	'JAN',
	'FEB',
	'MAR',
	'APR',
	'MAY',
	'JUN',
	'JUL',
	'AUG',
	'SEP',
	'OCT',
	'NOV',
	'DEC'
];
