// The reactive half of `device.ts`.
//
// Split from it on purpose, and the split is load-bearing twice over. Runes
// only compile in a `.svelte.ts` file — a `$state` in a plain `.ts` is an
// undefined call at runtime, which renders a blank page — and the corpus
// runner imports the pure half through Node's type-stripping loader, which
// knows nothing about runes. So the rules live where they can be replayed and
// the subscriptions live where they can be reactive.

import { COARSE_QUERY, keyboardOpen, readHandMode, type HandMode } from './device';

export { deviceType, type DeviceType, type HandMode } from './device';

const HAND_KEY = 'trophic-hand-mode';

/** Whether the on-screen keyboard is up, kept current. */
export function virtualKeyboard() {
	const state = $state({ open: false });

	$effect(() => {
		const vv = window.visualViewport;
		if (!vv) return; // desktop, and an iPad with a real keyboard
		const update = () => (state.open = keyboardOpen(window.innerHeight, vv.height));
		update();
		vv.addEventListener('resize', update);
		return () => vv.removeEventListener('resize', update);
	});

	return state;
}

/** Which hand is holding the phone. Persisted, and validated on read. */
export function handMode() {
	const state = $state({ mode: 'right' as HandMode });

	$effect(() => {
		try {
			state.mode = readHandMode(localStorage.getItem(HAND_KEY));
		} catch {
			/* no localStorage; the default stands */
		}
	});

	return {
		get mode() {
			return state.mode;
		},
		set(next: HandMode) {
			state.mode = next;
			try {
				localStorage.setItem(HAND_KEY, next);
			} catch {
				/* a preference is not worth an error */
			}
		}
	};
}

/** Re-exported so a screen needs one import. */
export { COARSE_QUERY };
