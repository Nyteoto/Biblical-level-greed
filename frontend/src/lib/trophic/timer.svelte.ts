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

/** The shape kept in localStorage. `startedAt` is null while paused, and
 *  `accumulatedMs` holds everything banked before the current run. */
type Running = {
	folderId: string;
	folderName: string;
	/** Epoch ms when the current run began, or null while paused. */
	startedAt: number | null;
	accumulatedMs: number;
};

const KEY = 'trophic-running-timer';

const state = $state({
	session: null as Running | null,
	loaded: false,
	/** Bumped by the interval purely to invalidate `elapsedMs`. The value is
	 *  meaningless; that it changed is the whole signal. */
	tick: 0
});

let handle: ReturnType<typeof setInterval> | null = null;

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
		return parsed;
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
	state.loaded = true;
}

/** Start ticking only while something is actually running. A paused timer and
 *  no timer cost the same: nothing. */
function sync() {
	const shouldRun = state.session?.startedAt != null;
	if (shouldRun && handle === null) {
		handle = setInterval(() => (state.tick += 1), 250);
	} else if (!shouldRun && handle !== null) {
		clearInterval(handle);
		handle = null;
	}
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
		/** Whole seconds, which is what gets logged. Floor rather than round:
		 *  the app should never claim a second that did not finish. */
		get elapsedSeconds() {
			void state.tick;
			return Math.floor(elapsed(state.session) / 1000);
		},

		/** Open a timer on a folder. Refuses to displace one already running on
		 *  a different folder — losing an unlogged session to a mis-tap is the
		 *  one thing this must not do. */
		start(folderId: string, folderName: string): boolean {
			load();
			if (state.session && state.session.folderId !== folderId) return false;
			if (state.session?.startedAt != null) return true;
			state.session = {
				folderId,
				folderName,
				startedAt: Date.now(),
				accumulatedMs: state.session?.accumulatedMs ?? 0
			};
			write(state.session);
			sync();
			return true;
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
			const seconds = Math.floor(elapsed(s) / 1000);
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
