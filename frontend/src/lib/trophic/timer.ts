// The clock's pure half: how a number of seconds is read.
//
// A plain `.ts` beside `timer.svelte.ts` for the reason `device.ts` sits beside
// `device.svelte.ts` — **a `$state` in a module that is imported outside the
// Svelte compiler is an undefined call at runtime.** `verify:ui` runs on Node's
// type stripping and imports the files the app ships, so anything it has to
// check has to be free of runes. The split is not tidiness: it is what lets
// these two have an oracle at all.
//
// Both formatters are covered by `localChecks()` in `scripts/verify-ui.ts`.
// Nothing in the corpus covers them — the source has no timer — and they are
// exactly the kind of thing that reads wrong for months without being noticed.

/** `1:04:09`, or `4:09` under an hour. Mono digits and no words: this is read
 *  at a glance from across a desk, and `1h 4m 9s` is three tokens to parse
 *  where a clock face is one. */
export function clockFace(totalSeconds: number): string {
	if (!Number.isFinite(totalSeconds)) return '0:00';
	const s = Math.max(0, Math.floor(totalSeconds));
	const hours = Math.floor(s / 3600);
	const minutes = Math.floor((s % 3600) / 60);
	const seconds = s % 60;
	const pad = (n: number) => String(n).padStart(2, '0');
	return hours > 0 ? `${hours}:${pad(minutes)}:${pad(seconds)}` : `${minutes}:${pad(seconds)}`;
}

/** `3h 20m`, `48m`, `—`. What a total reads as beside an entry count, where the
 *  seconds are noise and the unit has to be said out loud.
 *
 *  An em dash rather than `0h` for nothing at all: a project you have not
 *  clocked has no number, and printing a zero invites you to read it as a
 *  score.
 *
 *  **A missing number reads as no number, not as `NaNh NaNm`.** That is not
 *  defensive padding: this app ships a gitignored `frontend/build` against a
 *  separately-started backend on two operating systems, so a screen drawn by a
 *  client that is one deploy ahead of its server is a normal state here rather
 *  than an impossible one — it is why `EXPECTED_API` exists. A field the
 *  server has not learnt to send yet should read as nothing to report. */
export function duration(totalSeconds: number): string {
	if (!Number.isFinite(totalSeconds)) return '—';
	const s = Math.max(0, Math.floor(totalSeconds));
	if (s === 0) return '—';
	// Under a minute reads in seconds, and this has to come *before* the
	// rounding below: `Math.round(45 / 60)` is 1, so a 45-second session would
	// otherwise report a minute it never ran.
	if (s < 60) return `${s}s`;
	const hours = Math.floor(s / 3600);
	const minutes = Math.round((s % 3600) / 60);
	// 59m30s rounds to 60m, which should read as an hour rather than as
	// `0h 60m`. Carrying here is cheaper than a special case at every call site.
	if (minutes === 60) return `${hours + 1}h`;
	if (hours === 0) return minutes === 0 ? `${s}s` : `${minutes}m`;
	return minutes === 0 ? `${hours}h` : `${hours}h ${minutes}m`;
}
