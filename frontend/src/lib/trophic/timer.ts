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

// ── The pomodoro ──────────────────────────────────────────────────────────
//
// A cycle is one work stretch followed by one rest stretch, repeating. The
// whole of it is derived from a single number — how long the timer has been
// running — and that is the point rather than an economy.
//
// **The phase is computed, never driven by a callback.** The obvious build is
// a `setTimeout` for the end of the work stretch that flips a flag and sets
// the next one. It is wrong here for the same reason an accumulating tick is
// wrong for the clock: a background tab's timers are throttled and a sleeping
// phone's do not fire at all, so a phone locked halfway through a 50-minute
// stretch wakes with the work phase still "running" an hour later. Deriving
// the phase from elapsed time means the answer after any sleep of any length
// is simply correct, and the only thing the interval does is ask again.
//
// It follows that a phase change can be discovered *late* — the tab was asleep
// across it. `timer.svelte.ts` handles what that means for the sound.

export type Phase = 'work' | 'rest';

export interface PomodoroState {
	phase: Phase;
	/** Milliseconds left in the current phase. Counts down. */
	remainingMs: number;
	/** Work done so far, across every completed stretch plus the current one
	 *  if it is a work stretch. **Rest is not in here**, which is the whole
	 *  reason this function exists: what gets written to the log is time
	 *  worked, and a pomodoro that logged its own breaks would make an hour at
	 *  the desk read as an hour and ten. */
	workedMs: number;
	/** Completed work+rest cycles. Drawn as a row of marks. */
	cycles: number;
}

export function pomodoroAt(elapsedMs: number, workMs: number, restMs: number): PomodoroState {
	const elapsed = Number.isFinite(elapsedMs) ? Math.max(0, elapsedMs) : 0;
	const work = Number.isFinite(workMs) ? Math.max(0, workMs) : 0;
	const rest = Number.isFinite(restMs) ? Math.max(0, restMs) : 0;
	const cycle = work + rest;

	// No cycle to be in. A zero-length pomodoro is a stopwatch that has been
	// asked a nonsensical question; answer it as work with nothing left rather
	// than dividing by nothing.
	if (cycle <= 0) return { phase: 'work', remainingMs: 0, workedMs: elapsed, cycles: 0 };

	const cycles = Math.floor(elapsed / cycle);
	const position = elapsed - cycles * cycle;
	const working = position < work;

	return {
		phase: working ? 'work' : 'rest',
		remainingMs: working ? work - position : cycle - position,
		// Completed cycles contributed a whole work stretch each. The current
		// one contributes where it has got to, or all of it once rest began.
		workedMs: cycles * work + (working ? position : work),
		cycles
	};
}
