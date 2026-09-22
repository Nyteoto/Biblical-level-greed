// What makes a draft committable, said on the page as the server says it.
//
// The server is the authority — `day.missing` in `backend/app/day.py` refuses
// the commit whatever this answers. This copy exists so the checklist can
// shrink while you type rather than after you press. Keep the two lists
// saying the same things in the same words; the server's refusal is printed
// verbatim, and a checklist that disagreed with it would be the page arguing
// with itself.

import type { Draft } from '$lib/api';

// Python's `\w`: any letter or digit, in any script.
const FILLED = /[\p{L}\p{N}_]/u;

export function missing(draft: Draft, pictures: number): string[] {
	const gaps: string[] = [];
	if (!FILLED.test(draft.body)) gaps.push('the record');
	if (!FILLED.test(draft.wish)) gaps.push('what the next Instance should do');
	if (!FILLED.test(draft.signature)) gaps.push('the signature');
	if (draft.mood === null) gaps.push('how you feel, from 1 to 10');
	if (pictures < 1) gaps.push('at least one picture');
	return gaps;
}

/** `Tuesday, 22 September 2026` — the date as the printed Record states it. */
export function longDay(day: string): string {
	const [y, m, d] = day.split('-').map(Number);
	return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('en-GB', {
		weekday: 'long',
		day: 'numeric',
		month: 'long',
		year: 'numeric',
		timeZone: 'UTC'
	});
}

/** `2h 14m`, `9m`, `40s` — how long until something, at a glance. */
export function until(ms: number): string {
	const s = Math.max(0, Math.floor(ms / 1000));
	const h = Math.floor(s / 3600);
	const m = Math.floor((s % 3600) / 60);
	if (h) return `${h}h ${String(m).padStart(2, '0')}m`;
	if (m) return `${m}m ${String(s % 60).padStart(2, '0')}s`;
	return `${s}s`;
}

/** What the Portal says about a day that ended, by how it ended. */
export function epitaph(reason: string | null): string {
	switch (reason) {
		case 'left':
			return 'The sitting was abandoned. The page was left, and the day went with it.';
		case 'silent':
			return 'The sitting fell silent. No word came back in time, and the day was closed.';
		case 'deadline':
			return 'Twenty-three hundred came and nothing was committed.';
		case 'corrupt':
			return 'The day could not be read back. It has been treated as though it did not happen.';
		default:
			return 'No one woke in time to keep this day.';
	}
}
