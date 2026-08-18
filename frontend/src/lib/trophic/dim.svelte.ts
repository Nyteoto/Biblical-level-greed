// Whether the chrome is standing back because a line is being written.
//
// This was local state on the capture page, which was right while the only
// things that faded were that page's own header and syntax bar. The standing
// banner is drawn by the layout and has to fade with them — a strip that stays
// lit while everything around it goes dark is the one thing left on screen,
// which is the opposite of what the dim is for.
//
// Only the capture screen ever sets it, and it clears on the way out: leaving
// mid-fade would otherwise leave the banner invisible on the next screen with
// nothing there to bring it back.

const state = $state({ on: false });

export function uiDim() {
	return {
		get on() {
			return state.on;
		},
		set(next: boolean) {
			state.on = next;
		}
	};
}
