// The reactive half of the pin: which folder is currently claiming captures.
//
// localStorage, and device-local on purpose. "What I am working on right now"
// is a fact about this machine at this hour, not about the data — putting it in
// the log would mean an event every time you changed your mind, and a pin you
// set on the iPad would silently reroute what you type at the desk.
//
// One module-level store rather than a factory, unlike `handMode()`: the pin is
// read by the capture bar and could be shown anywhere else, and two independent
// copies of it would drift.

const KEY = 'trophic-pinned-folder';

const state = $state({ id: null as string | null, loaded: false });

function read(): string | null {
	try {
		return localStorage.getItem(KEY);
	} catch {
		return null;
	}
}

export function pinned() {
	// Lazily, and once: this is imported by a component that may render before
	// the browser exists, and a pin that has not been read yet is `null`, which
	// is also the value of no pin.
	if (!state.loaded && typeof localStorage !== 'undefined') {
		state.id = read();
		state.loaded = true;
	}
	return {
		get id() {
			return state.id;
		},
		set(next: string | null) {
			state.id = next;
			try {
				if (next) localStorage.setItem(KEY, next);
				else localStorage.removeItem(KEY);
			} catch {
				/* a preference is not worth an error */
			}
		}
	};
}
