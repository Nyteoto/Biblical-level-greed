// The persistent banner's state, held once for the whole app.
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
