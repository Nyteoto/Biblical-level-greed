// The persistent banner's state, held once for the whole app.
//
// Named `banner-state` and not `banner`, only because `Banner.svelte` sits
// beside it. Windows resolves paths case-insensitively, so `./banner.svelte`
// found the component rather than this module and the build stopped on a
// missing export that is plainly present on Linux. Every other store here
// keeps the short name; this one cannot while it shares a word with a
// component in the same directory.
//
// A module-level store rather than a per-component one, and for the same reason
// the pin is: the banner is drawn once in `+layout.svelte` but its contents are
// changed from all over — capturing a `--todo` on the capture screen, ticking
// one in the journal, queueing one from a hold. Two copies of this would drift
// within a keystroke of each other.
//
// It does not poll on a short timer. Everything that can change what the banner
// says is something the user just did in this tab, so `refresh()` after those
// is both sufficient and immediate; a timer would spend a request a second to
// discover nothing. The one thing no action causes is the day rolling over
// underneath a countdown, which is what the slow tick is for — a banner that
// says `1 day left` the morning after is worse than one that costs a request
// every quarter of an hour.

import { getBanner, type BannerState } from './api';

const SLOW_TICK = 15 * 60 * 1000;

const state = $state({
	data: null as BannerState | null,
	/** Bumped when a promise has just been written. The strip watches this and
	 *  blinks; nothing else reads it, and the number itself means nothing
	 *  beyond "it changed". A counter rather than a boolean because two todos
	 *  captured in a row are two announcements, and a flag set twice is one. */
	landed: 0,
	// Never surfaced. A banner that cannot reach the server should disappear
	// rather than announce itself: it is furniture on every screen, and
	// furniture that reports its own failures is worse than furniture missing.
	failed: false
});

let inflight: Promise<void> | null = null;
let timer: ReturnType<typeof setInterval> | null = null;

async function load() {
	try {
		state.data = await getBanner();
		state.failed = false;
	} catch {
		state.failed = true;
	}
}

export function banner() {
	return {
		get data() {
			return state.data;
		},
		get landed() {
			return state.landed;
		},
		/**
		 * Say that the line just captured carried a `--todo`.
		 *
		 * The strip is standing furniture — it is on the screen already, saying
		 * what is owed — so a promise arriving in it changes nothing you would
		 * notice at the moment you are least likely to look, which is directly
		 * after pressing enter on the thought you were holding. This is the
		 * strip putting its hand up for a second.
		 *
		 * Separate from `refresh()` on purpose: most refreshes are not news.
		 * Ticking one off, arriving on a screen, the quarter-hour tick — none of
		 * those should make the banner announce itself, and a refresh that
		 * blinked would make the app twitch every fifteen minutes.
		 */
		announce() {
			state.landed += 1;
		},
		/** Coalesced: several callers refreshing in the same tick share one
		 *  request, which is the normal case after a capture that both the page
		 *  and the banner want to react to. */
		refresh() {
			if (!inflight) {
				inflight = load().finally(() => {
					inflight = null;
				});
			}
			return inflight;
		},
		/** Called once, by the layout. The interval is cleared on teardown so a
		 *  hot reload does not leave a second one running. */
		start() {
			this.refresh();
			if (timer === null) timer = setInterval(() => this.refresh(), SLOW_TICK);
			return () => {
				if (timer !== null) clearInterval(timer);
				timer = null;
			};
		}
	};
}
