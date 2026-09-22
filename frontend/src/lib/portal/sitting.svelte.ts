// The one sitting a day gets, as the page holds it.
//
// **Memory only, on purpose.** The token and the draft live in this module and
// nowhere else — not `localStorage`, not `sessionStorage`, not the URL. A
// reload therefore loses both, and that is the rule rather than a limitation:
// the Record has to be written in one sitting, and the server keeps no copy
// of the text to resume from. Anything that survived a reload would be a way
// around it.
//
// **The page reports its own departure, and the heartbeat reports the rest.**
// `pagehide` sends a beacon that ends the day at once — a reload, a closed
// tab, navigating away. The heartbeat covers what a page cannot report: a
// crash, a laptop lid, a phone that died. The server's grace is several beats
// long, so a phone that locks for a minute, or a camera that takes the tab
// away while a clip is recorded, does not end anything.
//
// Module-level rather than a component's, so the draft outlives the component
// that draws it. The shell hides every link off the page while a sitting is
// open, but a component re-mounting must not be what costs somebody their day.

import { ApiError, beat, leave, type Draft } from '$lib/api';

const BEAT_MS = 20_000;

let token = $state<string | null>(null);
let ended = $state<string | null>(null);
let timer: ReturnType<typeof setInterval> | null = null;

export const draft = $state<Draft>({
	body: '',
	wish: '',
	signature: '',
	mood: null,
	captions: {}
});

function onPageHide() {
	if (token) leave(token);
}

// A last chance for a reload that was not meant. The browser draws its own
// "leave site?" dialog; the words cannot be ours, but the pause can.
function onBeforeUnload(event: BeforeUnloadEvent) {
	if (!token) return;
	event.preventDefault();
	event.returnValue = '';
}

async function pulse() {
	if (!token) return;
	try {
		await beat(token);
	} catch (err) {
		// 410 and 403 are the server saying the sitting is over. Anything else
		// — a dropped network — is left to the grace: one missed beat is not a
		// departure, and the next one may land.
		if (err instanceof ApiError && (err.status === 410 || err.status === 403)) {
			end(err.message);
		}
	}
}

/** Hold a sitting the server just opened. */
export function hold(t: string, signature: string) {
	token = t;
	ended = null;
	draft.body = '';
	draft.wish = '';
	draft.signature = signature;
	draft.mood = null;
	draft.captions = {};
	addEventListener('pagehide', onPageHide);
	addEventListener('beforeunload', onBeforeUnload);
	timer = setInterval(pulse, BEAT_MS);
	// A tab coming back from the background beats at once, rather than waiting
	// out whatever is left of an interval the browser throttled while it was away.
	document.addEventListener('visibilitychange', onVisible);
}

function onVisible() {
	if (document.visibilityState === 'visible') void pulse();
}

/** Let go: sealed, or over. Nothing is sent; the server already knows. */
export function end(reason: string | null = null) {
	token = null;
	ended = reason;
	if (timer) clearInterval(timer);
	timer = null;
	removeEventListener('pagehide', onPageHide);
	removeEventListener('beforeunload', onBeforeUnload);
	document.removeEventListener('visibilitychange', onVisible);
}

export const sitting = {
	get token() {
		return token;
	},
	get ended() {
		return ended;
	}
};
