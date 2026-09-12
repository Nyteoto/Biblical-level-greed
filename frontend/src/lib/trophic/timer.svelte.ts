// The running timer: the one piece of this feature that is not in the log.
//
// **A session enters the log when it is stopped, and not before.** While it
// runs it is a draft, exactly like the text in the capture bar — it lives in
// this machine's browser, it is not a fact about what you did until you say it
// is, and a timer left running overnight and abandoned is not a nine-hour
// session that happens to be unfinished. That is also why there is no `start`
// event: an append-only log would then carry a start with no end for every
// timer anyone ever forgot, and no fold could tell those from the real ones.
//
// The cost of that choice is the honest one: close the tab mid-session on a
// machine and the elapsed time is on that machine only. localStorage is what
// makes that survive a reload, a navigation and a crash, which covers
// everything except clearing site data.
//
// **Elapsed is computed from wall-clock stamps, never accumulated by a tick.**
// A background tab has its timers throttled to once a second at best and often
// far worse, and a phone that sleeps stops firing them altogether — an
// incrementing counter would quietly under-report exactly the long sessions
// this is for. The interval below only tells the screen to re-read the clock;
// it never *is* the clock.

import { armChime, chime } from './chime';
import { pomodoroAt, type Phase } from './timer';

/** The shape kept in localStorage. `startedAt` is null while paused, and
 *  `accumulatedMs` holds everything banked before the current run.
 *
 *  **`accumulatedMs` is wall-clock time, not work time**, in both modes. In a
 *  pomodoro the split between work and rest is *derived* from it by
 *  `pomodoroAt`, which is what lets the phase be correct after any sleep of
 *  any length. Storing "work so far" instead would mean maintaining it from a
 *  callback, and the callback is the thing that does not fire. */
type Running = {
	folderId: string;
	folderName: string;
	/** Epoch ms when the current run began, or null while paused. */
	startedAt: number | null;
	accumulatedMs: number;
	/** `stopwatch` counts up and logs everything. `pomodoro` alternates work
	 *  and rest, and logs only the work. */
	mode: Mode;
	/** The two stretch lengths, in ms. Carried on the session rather than read
	 *  from the preference at render time, so that changing the default
	 *  mid-session cannot retroactively re-cut a pomodoro that is already
	 *  running — the phase you are in would jump, and the work already banked
	 *  would change value. */
	workMs: number;
	restMs: number;
};

export type Mode = 'stopwatch' | 'pomodoro';

const KEY = 'trophic-running-timer';
/** The lengths a *new* pomodoro starts with. A preference about this machine,
 *  like the pin — not a fact about what you did. */
const PREF_KEY = 'trophic-pomodoro-lengths';
const MUTE_KEY = 'trophic-timer-muted';

/** Fifty and ten. The classic twenty-five is tuned for a task you are dreading;
 *  the work this app is used for is the kind you have to be pulled out of, and
 *  a fifty-minute stretch is one pass at something rather than a fragment of
 *  one. Both are editable and neither is enforced. */
export const DEFAULT_WORK_MIN = 50;
export const DEFAULT_REST_MIN = 10;

const state = $state({
	session: null as Running | null,
	loaded: false,
	muted: false,
	/** The lengths a new pomodoro will be started with, in minutes. */
	workMin: DEFAULT_WORK_MIN,
	restMin: DEFAULT_REST_MIN,
	/** Bumped by the interval purely to invalidate `elapsedMs`. The value is
	 *  meaningless; that it changed is the whole signal. */
	tick: 0
});

let handle: ReturnType<typeof setInterval> | null = null;
/** The phase the last tick saw. Module state and deliberately **not**
 *  persisted: a reload should not sound a chime for a boundary that was
 *  crossed and heard an hour ago. `null` means "nothing seen yet", which is
 *  the state a fresh load is in and the reason the first tick after a reload
 *  is silent. */
let lastPhase: Phase | null = null;

function read(): Running | null {
	try {
		const raw = localStorage.getItem(KEY);
		if (!raw) return null;
		const parsed = JSON.parse(raw) as Running;
		// A stored shape from a future or broken version reads as no timer
		// rather than throwing during boot — the same bargain `retry-queue.ts`
		// makes with its own storage.
		if (typeof parsed?.folderId !== 'string') return null;
		if (typeof parsed?.accumulatedMs !== 'number') return null;
		// A session stored before the pomodoro existed has no mode. It was a
		// stopwatch, and reading it as one is what keeps a timer that was
		// running across the upgrade.
		return {
			...parsed,
			mode: parsed.mode === 'pomodoro' ? 'pomodoro' : 'stopwatch',
			workMs: typeof parsed.workMs === 'number' ? parsed.workMs : DEFAULT_WORK_MIN * 60000,
			restMs: typeof parsed.restMs === 'number' ? parsed.restMs : DEFAULT_REST_MIN * 60000
		};
	} catch {
		return null;
	}
}

function write(next: Running | null) {
	try {
		if (next) localStorage.setItem(KEY, JSON.stringify(next));
		else localStorage.removeItem(KEY);
	} catch {
		/* the timer still runs; it just will not survive a reload */
	}
}

function load() {
	if (state.loaded || typeof localStorage === 'undefined') return;
	state.session = read();
	try {
		state.muted = localStorage.getItem(MUTE_KEY) === '1';
		const raw = localStorage.getItem(PREF_KEY);
		if (raw) {
			const parsed = JSON.parse(raw) as { workMin?: number; restMin?: number };
			if (Number.isFinite(parsed?.workMin)) state.workMin = clampMinutes(parsed.workMin!);
			if (Number.isFinite(parsed?.restMin)) state.restMin = clampMinutes(parsed.restMin!);
		}
	} catch {
		// The defaults are good defaults.
	}
	state.loaded = true;
}

/** One minute to four hours. The floor is what stops a mistyped `0` making a
 *  pomodoro that changes phase every frame and chimes forever; the ceiling is
 *  well under the twelve-hour session the server refuses outright. */
function clampMinutes(value: number): number {
	if (!Number.isFinite(value)) return 1;
	return Math.min(240, Math.max(1, Math.round(value)));
}

/** Start ticking only while something is actually running. A paused timer and
 *  no timer cost the same: nothing. */
function sync() {
	const shouldRun = state.session?.startedAt != null;
	if (shouldRun && handle === null) {
		handle = setInterval(() => {
			state.tick += 1;
			watchPhase();
		}, 250);
	} else if (!shouldRun && handle !== null) {
		clearInterval(handle);
		handle = null;
	}
	if (!shouldRun) lastPhase = null;
}

/**
 * Sound the boundary when the derived phase changes.
 *
 * It lives in the store rather than in `Timer.svelte` on purpose: the point of
 * `back — keep running` is that the timer goes on while you use the app, and a
 * chime that only fired on the screen you had left would be a chime that never
 * fired when it mattered. The store outlives every component in the tab.
 *
 * A boundary crossed while the tab was asleep is announced **when the tab wakes
 * up**, once, however many boundaries were actually missed. That is a decision
 * rather than a limitation: the alternative is a burst of chimes for stretches
 * that are long over, and what you want to be told on waking is which phase you
 * are in now.
 */
function watchPhase() {
	const s = state.session;
	if (!s || s.mode !== 'pomodoro' || s.startedAt === null) {
		lastPhase = null;
		return;
	}
	const { phase } = pomodoroAt(elapsed(s), s.workMs, s.restMs);
	// The first observation of a session only records where it is; there is no
	// boundary behind it to announce.
	if (lastPhase !== null && phase !== lastPhase && !state.muted) chime(phase);
	lastPhase = phase;
}

function elapsed(session: Running | null): number {
	if (!session) return 0;
	const live = session.startedAt === null ? 0 : Date.now() - session.startedAt;
	// `max(0)` because a clock that has been set backwards — a phone crossing a
	// timezone, an NTP correction — would otherwise read as negative and show a
	// timer running backwards. The banked time is still right.
	return session.accumulatedMs + Math.max(0, live);
}

export function timer() {
	load();
	sync();
	return {
		get session() {
			return state.session;
		},
		get running() {
			return state.session?.startedAt != null;
		},
		/** Is a timer open on this particular folder? What the folder's own
		 *  button reads to know whether it says `start` or `resume`. */
		isOn(folderId: string) {
			return state.session?.folderId === folderId;
		},
		get elapsedMs() {
			// Touch the tick so this derived re-runs; see the note above.
			void state.tick;
			return elapsed(state.session);
		},
		/** Whole seconds on the clock, both modes. Floor rather than round: the
		 *  app should never claim a second that did not finish. */
		get elapsedSeconds() {
			void state.tick;
			return Math.floor(elapsed(state.session) / 1000);
		},

		/** **What actually gets logged.** In a stopwatch it is the whole
		 *  elapsed time; in a pomodoro it is the work stretches only, with
		 *  every break taken out. A pomodoro that logged its own rest would
		 *  make an hour at the desk read as an hour and ten, and the number on
		 *  the card would stop meaning "time worked". */
		get workedSeconds() {
			void state.tick;
			const s = state.session;
			if (!s) return 0;
			if (s.mode !== 'pomodoro') return Math.floor(elapsed(s) / 1000);
			return Math.floor(pomodoroAt(elapsed(s), s.workMs, s.restMs).workedMs / 1000);
		},

		/** Where the pomodoro is, or null in a stopwatch. Derived on every
		 *  read from the elapsed time, so it is correct after any sleep. */
		get pomodoro() {
			void state.tick;
			const s = state.session;
			if (!s || s.mode !== 'pomodoro') return null;
			return pomodoroAt(elapsed(s), s.workMs, s.restMs);
		},

		get mode(): Mode {
			return state.session?.mode ?? 'stopwatch';
		},

		// ── The lengths a new pomodoro gets, and the sound ────────────────
		get workMin() {
			return state.workMin;
		},
		get restMin() {
			return state.restMin;
		},
		get muted() {
			return state.muted;
		},
		setLengths(workMin: number, restMin: number) {
			state.workMin = clampMinutes(workMin);
			state.restMin = clampMinutes(restMin);
			try {
				localStorage.setItem(
					PREF_KEY,
					JSON.stringify({ workMin: state.workMin, restMin: state.restMin })
				);
			} catch {
				/* the lengths still apply to this session */
			}
		},
		setMuted(next: boolean) {
			state.muted = next;
			try {
				localStorage.setItem(MUTE_KEY, next ? '1' : '0');
			} catch {
				/* nothing to do */
			}
		},

		/** Open a timer on a folder. Refuses to displace one already running on
		 *  a different folder — losing an unlogged session to a mis-tap is the
		 *  one thing this must not do. */
		start(folderId: string, folderName: string, mode?: Mode): boolean {
			load();
			if (state.session && state.session.folderId !== folderId) return false;
			if (state.session?.startedAt != null) return true;
			// Unlock the audio device here, because here is where the user
			// gesture is. A chime forty minutes from now has no gesture near it
			// and a context created then would be born suspended.
			armChime();
			const resuming = state.session;
			state.session = {
				folderId,
				folderName,
				startedAt: Date.now(),
				accumulatedMs: resuming?.accumulatedMs ?? 0,
				// Resuming keeps the mode and the lengths it was started with;
				// only a fresh session reads the preference. Changing the
				// default mid-pomodoro would re-cut the cycle underneath it and
				// move work that has already been banked.
				mode: mode ?? resuming?.mode ?? 'stopwatch',
				workMs: resuming?.workMs ?? state.workMin * 60000,
				restMs: resuming?.restMs ?? state.restMin * 60000
			};
			write(state.session);
			sync();
			return true;
		},

		/** Swap a running session between counting up and running a cycle,
		 *  keeping the time already on it.
		 *
		 *  Allowed mid-session because the elapsed clock means the same thing
		 *  in both modes — what changes is how it is *cut*. Going to a pomodoro
		 *  mid-way does re-read the elapsed time as cycles, which will bank
		 *  less than the clock shows if a break falls inside it; that is
		 *  correct rather than surprising, and it is why the screen shows both
		 *  numbers. */
		setMode(mode: Mode) {
			const s = state.session;
			if (!s) return;
			state.session = {
				...s,
				mode,
				workMs: state.workMin * 60000,
				restMs: state.restMin * 60000
			};
			write(state.session);
			// The phase under the new mode has not been "seen" yet, so the next
			// tick records it silently instead of announcing a change that is
			// really just the mode switch.
			lastPhase = null;
		},

		pause() {
			const s = state.session;
			if (!s || s.startedAt === null) return;
			state.session = {
				...s,
				startedAt: null,
				accumulatedMs: elapsed(s)
			};
			write(state.session);
			sync();
		},

		/** Bank what has run so far and hand it back, clearing the timer. The
		 *  caller sends it; if that send fails it can start again from the
		 *  number it was given, because nothing here has been thrown away until
		 *  it returns. */
		stop(): { folderId: string; seconds: number } | null {
			const s = state.session;
			if (!s) return null;
			// Work, not clock. See `workedSeconds`.
			const seconds =
				s.mode === 'pomodoro'
					? Math.floor(pomodoroAt(elapsed(s), s.workMs, s.restMs).workedMs / 1000)
					: Math.floor(elapsed(s) / 1000);
			state.session = null;
			write(null);
			sync();
			return { folderId: s.folderId, seconds };
		},

		/** Throw the session away without logging it. Separate from `stop` so
		 *  the screen has to say which one it means. */
		discard() {
			state.session = null;
			write(null);
			sync();
		}
	};
}

// The formatters live in `timer.ts` — plain TypeScript, so `verify:ui` can
// import and check them without the Svelte compiler. Re-exported here so a
// component that wants the store and a format has one import to write.
export { clockFace, duration } from './timer';
