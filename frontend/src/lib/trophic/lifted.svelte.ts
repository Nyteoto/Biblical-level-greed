// Which tags are read back without their brackets.
//
// The set itself lives in the log — lifting is a decision about how your own
// writing reads, and one made on the desk should hold on the iPad — so unlike
// the pin and the folded headings this is *not* localStorage. What is here is
// the one copy of it the browser keeps, because every screen that draws a
// captured line needs the answer before it can draw one and none of them should
// be fetching it for itself.
//
// One module-level store rather than a factory, for the same reason as the pin:
// `ColorizedText` is rendered from four different screens and two copies of
// this would let one of them go on drawing brackets the other has dropped.
//
// It hydrates lazily and at most once per load. Everything renders correctly
// before it lands — an unhydrated set lifts nothing, which is exactly what the
// app did before any of this existed — and the answer arrives a frame later.

import { getVocab, liftTag } from './api';

const state = $state({ tags: new Set<string>(), asked: false });

export function lifted() {
	if (!state.asked && typeof fetch !== 'undefined') {
		state.asked = true;
		getVocab()
			.then((v) => (state.tags = new Set(v.lifted ?? [])))
			.catch(() => {
				// Offline, or a backend that has not come up yet. Brackets drawn
				// is the honest fallback: it is what was typed.
			});
	}
	return {
		/** `tag` is a token's inner value, which `tokenize` has already
		 *  lowercased — the same spelling the backend stores. */
		has(tag: string) {
			return state.tags.has(tag);
		},
		get all() {
			return state.tags;
		},
		/** Lift a tag or put it back, and hold what the server answers. The
		 *  reply carries the whole set rather than the one tag, so a second
		 *  window that lifted something else cannot be lost by this write. */
		async set(tag: string, on: boolean) {
			const { lifted: all } = await liftTag(tag, on);
			state.tags = new Set(all);
		},
		/** For a screen that has just read the set from somewhere else. */
		seed(tags: string[]) {
			state.asked = true;
			state.tags = new Set(tags);
		}
	};
}
