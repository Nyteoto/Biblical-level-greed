// The subject's shelf, held once for the whole app — and whether the picker
// is open.
//
// `shelf.ts` beside this is the *reading* of a shelf (which albums are loose,
// which sit under a heading); this is the shelf itself, fetched and shared.
// The names are close because they are about the same object from two sides,
// and neither is a good candidate for renaming.
//
// ## Why this is a store and not three fetches
//
// Map, the Log and Record each asked the server for `/shelf` on their own,
// for their own reasons — the totals, the assign menu's folder list, the year
// below. That was three round trips for one fact, and worse, three copies of
// it: rename a folder in the picker and the assign menu two screens away still
// said the old name until something else happened to refetch.
//
// The subject bar made that untenable rather than merely wasteful. It is drawn
// in the shell, it edits folders, and every lens under it reads the result —
// so there has to be one answer and one place that invalidates it. Same shape
// `banner-state.svelte.ts` uses, for the same reason: drawn once, changed from
// everywhere.
//
// It is keyed on the year because a shelf *is* a year's. Asking for a year it
// already holds is free; asking for a different one replaces it, because two
// years of shelf on screen at once is not a state this app has.

import { getShelf, getUnassignedTags, type Shelf, type UnassignedTag } from './api';

const state = $state({
	data: null as Shelf | null,
	/** Which year `data` is of, so a repeat ask costs nothing and a change is
	 *  noticed without comparing payloads. */
	year: '',
	/** The words pointed at nothing yet — Record's `Unclaimed` row and the
	 *  held panel's one retroactive edit.
	 *
	 *  Here for the reason the shelf is, one list down: both screens fetched
	 *  their own on mount and neither refetched, so pointing a tag at a folder
	 *  on Record left the picker still offering it. Not keyed on the year,
	 *  because a tag is claimed or it is not — but it changes on exactly the
	 *  edits the shelf does, so it is refreshed with it. */
	tags: [] as UnassignedTag[],
	/** Whether the folder picker is down. In the store rather than in
	 *  `SubjectBar` because the Log opens it: pressing that key with no folder
	 *  chosen has nothing to read, and the one press you need should already be
	 *  open rather than waiting behind a control you have not found yet. */
	picking: false,
	// Never surfaced, for the reason the banner's is not: the bar is furniture
	// on every lens, and furniture that reports its own failures is worse than
	// furniture that is quietly empty for a moment.
	failed: false
});

let inflight: Promise<void> | null = null;

async function load(year: string) {
	try {
		state.data = await getShelf(year);
		state.year = year;
		state.failed = false;
	} catch {
		state.failed = true;
	}
	// Separately and tolerantly. The loose tags are one row on Record and one
	// option in a held panel; a shelf that refused to draw because they could
	// not be fetched would be the tail wagging the dog.
	try {
		state.tags = (await getUnassignedTags()).tags;
	} catch {
		/* then there is simply nothing to claim */
	}
}

export function subject() {
	return {
		get data() {
			return state.data;
		},
		get tags() {
			return state.tags;
		},
		get picking() {
			return state.picking;
		},
		/** The shelf for `year`, fetched if it is not the one in hand. Coalesced,
		 *  so the bar and the lens under it asking in the same tick share one
		 *  request — which is the ordinary case on every navigation. */
		want(year: string) {
			if (state.year === year && state.data) return inflight ?? Promise.resolve();
			if (!inflight) {
				inflight = load(year).finally(() => {
					inflight = null;
				});
			}
			return inflight;
		},
		/** Ask again for the year in hand. What every folder edit calls, and the
		 *  reason a rename in the picker reaches the assign menu. */
		refresh() {
			const year = state.year;
			if (!year) return Promise.resolve();
			state.year = '';
			return this.want(year);
		},
		open() {
			state.picking = true;
		},
		close() {
			state.picking = false;
		},
		toggle() {
			state.picking = !state.picking;
		}
	};
}
