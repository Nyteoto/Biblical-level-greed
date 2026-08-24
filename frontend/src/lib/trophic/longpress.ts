// Long press — mobile's spelling of right-click.
//
// Ported from `hooks/useLongPress.ts` + `components/LongPressWrapper.tsx`,
// pinned by `long_press.json` (14 cases). Both numbers are kept: 500ms
// stationary to fire, 10px of slack. They matter in opposite directions —
// shorter, and a scroll that starts slowly opens a menu instead; longer, and
// it stops feeling like a press at all.
//
// The state machine is separate from the Svelte action so the corpus can
// drive it with a fake clock. Four behaviours it records that are easy to
// lose, every one of which is a bug that only shows up on a phone:
//
//   - **The move threshold is radial**, `hypot(dx, dy) > 10`, not per-axis. A
//     diagonal drift of 8,8 is 11.3px and cancels; 8px on one axis does not.
//   - **Cancelling is final.** Drifting out of the slack and back does not
//     restart the press.
//   - **A second finger cancels**, and the running press is cleared *before*
//     the finger count is checked — so two fingers both kill the press in
//     flight and refuse to start a new one.
//   - **The position is captured at touchstart**, so the menu opens where the
//     finger landed rather than where it had drifted to when the timer fired.
//
// And one on the way out: after a press fires, exactly one following click is
// swallowed and the flag resets. Leaving it set eats the user's next real tap.

export type Point = { x: number; y: number };
export type LongPressAt = (x: number, y: number) => void;

/** Injected so the corpus can advance time without waiting for it. */
export type Timers = {
	set(fn: () => void, ms: number): unknown;
	clear(id: unknown): void;
};

const REAL_TIMERS: Timers = {
	set: (fn, ms) => setTimeout(fn, ms),
	clear: (id) => clearTimeout(id as ReturnType<typeof setTimeout>)
};

export const LONG_PRESS_DELAY = 500;
export const LONG_PRESS_MOVE = 10;

export class LongPress {
	private timer: unknown = null;
	private origin: Point | null = null;
	private fired = false;
	private onfire: LongPressAt;
	private delay: number;
	private moveThreshold: number;
	private timers: Timers;

	// Fields assigned in the body rather than declared as parameter
	// properties: `scripts/verify-ui.ts` runs this file through Node's
	// type-stripping loader, which is erasure-only and rejects the shorthand.
	constructor(
		onfire: LongPressAt,
		delay = LONG_PRESS_DELAY,
		moveThreshold = LONG_PRESS_MOVE,
		timers: Timers = REAL_TIMERS
	) {
		this.onfire = onfire;
		this.delay = delay;
		this.moveThreshold = moveThreshold;
		this.timers = timers;
	}

	private clear() {
		if (this.timer !== null) this.timers.clear(this.timer);
		this.timer = null;
	}

	start(points: Point[]) {
		// Clear first, check the count second — see the note above.
		this.clear();
		if (points.length !== 1) return;
		const at = { x: points[0].x, y: points[0].y };
		this.origin = at;
		this.fired = false;
		this.timer = this.timers.set(() => {
			this.fired = true;
			this.onfire(at.x, at.y);
		}, this.delay);
	}

	move(points: Point[]) {
		if (!this.origin || points.length === 0) return;
		const dx = points[0].x - this.origin.x;
		const dy = points[0].y - this.origin.y;
		if (Math.hypot(dx, dy) > this.moveThreshold) this.clear();
	}

	end() {
		this.clear();
		this.origin = null;
	}

	/** The synthetic click that follows a fired press. True when swallowed. */
	click(): boolean {
		if (!this.fired) return false;
		this.fired = false;
		return true;
	}
}

// This file is the state machine and nothing else now.
//
// It used to also export a `longpress` Svelte action, which ran a *second*
// `LongPress` per node alongside the global one in `HoldRing` and then claimed
// the global one so the ring would not draw its × over the menu the node had
// already opened. Two timers for one gesture, agreeing only because both were
// constructed with the same delay. Answering a hold is one action now — see
// `hold.ts` — and this is the one clock behind it, which is what the fourteen
// fixtures describe.
