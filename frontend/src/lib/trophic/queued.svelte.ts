// Which todo the banner should show next, when you have said so explicitly.
//
// localStorage and device-local, on exactly the pin's argument: what you have
// decided to do next is a fact about this machine at this hour, not about the
// data. The todo itself is in the log — writing it was a decision. Which of ten
// open ones you want in front of you right now is not, and an event for it
// would put a permanent line in an append-only file every time you changed your
// mind about the order.
//
// Stored as `entryId:line`, because that pair is what identifies a todo: a todo
// is a *line* in an entry, and one entry can carry several.
//
// Nothing here validates that the todo still exists. The banner resolves the
// key against the open list it already has and falls back to oldest-first when
// it does not match — which covers the todo being checked off, its entry being
// deleted, or a key left behind by an older version of this file. A queue that
// points at nothing is not an error state, it is just no longer a preference.

const KEY = 'trophic-queued-todo';

const state = $state({ key: null as string | null, loaded: false });

function read(): string | null {
	try {
		return localStorage.getItem(KEY);
	} catch {
		return null;
	}
}

export const todoKey = (entryId: string, line: number) => `${entryId}:${line}`;

export function queuedTodo() {
	// Lazily and once, like the pin: imported by a component that can render
	// before the browser exists.
	if (!state.loaded && typeof localStorage !== 'undefined') {
		state.key = read();
		state.loaded = true;
	}
	return {
		get key() {
			return state.key;
		},
		is(entryId: string, line: number) {
			return state.key === todoKey(entryId, line);
		},
		set(entryId: string, line: number) {
			state.key = todoKey(entryId, line);
			try {
				localStorage.setItem(KEY, state.key);
			} catch {
				// Private mode or a full quota. It holds for this session and is
				// simply not remembered, which is the harmless direction to fail.
			}
		},
		clear() {
			state.key = null;
			try {
				localStorage.removeItem(KEY);
			} catch {
				/* as above */
			}
		}
	};
}
