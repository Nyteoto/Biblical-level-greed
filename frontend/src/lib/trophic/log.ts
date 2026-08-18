/**
 * How the album screen decides what a day looks like.
 *
 * Split out of the component for the reason the rest of this port's behaviour
 * is: **anything that decides what a screen shows belongs in a module the
 * corpus (or a local check) can replay; the component keeps the DOM, the
 * timers and the measuring.** None of the corpus's fixtures describe this
 * screen — it is this port's own invention — so `verify-ui.ts`'s local checks
 * are the oracle, and they exist because a quiet-stretch bug is exactly the
 * kind that hides: it swallows days rather than crashing.
 *
 * Two shapes, and the rule that separates them:
 *
 *   - The **lead day** is the newest day in the album and gets everything: the
 *     photograph, the caption, the ribbon, the timestamped lines.
 *   - Every day after it is a **light row** — a date, a line, a time — unless
 *     it joins a **quiet stretch**, which is a run of consecutive light days
 *     that had a line or two and no media at all.
 *
 * A quiet stretch is a merge, never a hide. The strip says how many lines it
 * is holding and expands into exactly the rows it replaced; the same days with
 * the merge switched off in Settings render one after another unchanged. If
 * expanding a stretch ever shows you something you could not have reached with
 * the setting off, this file is wrong.
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

/** A day quiet enough to be worth merging: a line or two, and nothing made. */
export function isQuiet(day: Day): boolean {
	return day.media.length === 0 && day.entries.length <= 2;
}

export type Stretch = { kind: 'stretch'; days: Day[] };
export type Single = { kind: 'day'; day: Day };
export type Row = Single | Stretch;

/**
 * Fold runs of quiet days into stretches. A run of one is left alone — a strip
 * saying "quiet stretch · 1 line" is longer than the line it is hiding.
 *
 * `merge = false` is the Settings switch turned off, and it returns every day
 * as its own row. That is the whole implementation of that setting: the same
 * input, one branch, and nothing stored either way.
 */
export function foldQuiet(days: Day[], merge = true): Row[] {
	if (!merge) return days.map((day) => ({ kind: 'day', day }) as Single);

	const out: Row[] = [];
	let run: Day[] = [];

	const flush = () => {
		if (run.length > 1) out.push({ kind: 'stretch', days: run });
		else if (run.length === 1) out.push({ kind: 'day', day: run[0] });
		run = [];
	};

	for (const day of days) {
		if (isQuiet(day)) run.push(day);
		else {
			flush();
			out.push({ kind: 'day', day });
		}
	}
	flush();
	return out;
}

/**
 * `Mon 3 – Wed 12`, or `9 Feb – 28 Jul` when the stretch crosses a month.
 *
 * The days are newest first, so the range reads from the older end — a stretch
 * is described the way it was lived. The month is dropped inside one month
 * because the header above already says which; it comes back the moment the
 * two ends are in different ones, where leaving it off makes the label a
 * genuine lie about how much time the strip is holding.
 */
export function stretchLabel(days: Day[]): string {
	const first = days[days.length - 1].key;
	const last = days[0].key;
	if (first.slice(0, 7) === last.slice(0, 7)) {
		return `${shortDay(first)} – ${shortDay(last)}`;
	}
	return `${withMonth(first)} – ${withMonth(last)}`;
}

/** `9 Feb`. Weekday dropped: two weekdays and two months in one strip is more
 *  than the label can carry at 13px. */
function withMonth(key: string): string {
	const [y, m, d] = key.split('-').map(Number);
	return new Date(y, m - 1, d).toLocaleDateString(undefined, {
		day: 'numeric',
		month: 'short'
	});
}

export function stretchTally(days: Day[]): string {
	const lines = days.reduce((n, day) => n + day.entries.length, 0);
	return `Quiet stretch · ${lines} ${lines === 1 ? 'line' : 'lines'}, no media`;
}

/** `Mon 3`. Weekday and date, no month: a stretch never crosses one by much
 *  and the header above already says which one it is. */
export function shortDay(key: string): string {
	const [y, m, d] = key.split('-').map(Number);
	return new Date(y, m - 1, d).toLocaleDateString(undefined, {
		weekday: 'short',
		day: 'numeric'
	});
}

/** `Sat 15 Aug`. The headline form, and the light rows' date column. */
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
