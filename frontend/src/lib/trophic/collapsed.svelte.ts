// Which shelf groups are folded shut, per year.
//
// localStorage and device-local, for the same reason the pin is: whether a
// heading is open right now is a fact about this machine at this hour, not
// about the data. The group itself *is* in the log — `set-group` is an event
// like any other, because which group a folder belongs to is a decision you
// made. Whether you have it folded shut while you look for something else is
// not, and an event for it would put a line in the log every time you clicked
// a chevron.
//
// Keyed by `year + ':' + name` rather than by name alone. A group called
// `Field` in 2025 and one in 2026 are separate arrangements — that is the whole
// point of grouping being per-year — so folding one must not fold the other.
//
// Renaming is not handled and does not need to be: a renamed group is a new
// key, so it comes back open, which is the harmless direction to fail in.

const KEY = 'trophic-collapsed-groups';

const state = $state({ shut: new Set<string>(), loaded: false });

function read(): Set<string> {
	try {
		const raw = localStorage.getItem(KEY);
		if (!raw) return new Set();
		const parsed = JSON.parse(raw);
		return Array.isArray(parsed) ? new Set(parsed.filter((k) => typeof k === 'string')) : new Set();
	} catch {
		// A corrupt or unreadable value is not worth a failure mode. Everything
		// open is the state this began in.
		return new Set();
	}
}

const keyFor = (year: string | null, name: string) => `${year ?? 'all'}:${name}`;

export function collapsedGroups() {
	// Lazily and once, like the pin: this is imported by a component that can
	// render before the browser exists.
	if (!state.loaded && typeof localStorage !== 'undefined') {
		state.shut = read();
		state.loaded = true;
	}
	return {
		isShut(year: string | null, name: string) {
			return state.shut.has(keyFor(year, name));
		},
		toggle(year: string | null, name: string) {
			// A new Set rather than a mutation: `$state` tracks the reference,
			// and adding to the existing one updates nothing on screen.
			const next = new Set(state.shut);
			const key = keyFor(year, name);
			if (next.has(key)) next.delete(key);
			else next.add(key);
			state.shut = next;
			try {
				localStorage.setItem(KEY, JSON.stringify([...next]));
			} catch {
				// Private mode, or a full quota. The fold still works for this
				// session; it just will not be remembered.
			}
		}
	};
}
