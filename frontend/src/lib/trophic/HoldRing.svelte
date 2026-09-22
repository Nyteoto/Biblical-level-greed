<script lang="ts">
	/**
	 * The hold gesture, drawn where the finger is.
	 *
	 * A ring spawns under the touch and fills its perimeter clockwise from six
	 * o'clock. When it closes, the hold has happened; let go early and it is
	 * gone. It exists so a press-and-hold can mean "properties of this" anywhere
	 * in the app, and so that meaning is *visible* while it is being asked for —
	 * an invisible 500ms timer is indistinguishable from a dropped touch.
	 *
	 * **The timing is not new.** `LongPress` is the corpus-pinned state machine
	 * this app already had for mobile's right-click — 500ms stationary, 10px of
	 * radial slack, cancelling is final, a second finger kills it — and this
	 * drives the ring from exactly that. Fourteen fixtures describe those rules
	 * and every one of them is a bug that only shows up on a phone, so the ring
	 * inherits them rather than approximating them. It is also why the ring and
	 * the existing per-node long press can never disagree about what a hold is.
	 *
	 * The ring appears ~130ms in, not immediately, and the fill still starts at
	 * the touch. An ordinary tap is over long before it shows, so tapping does
	 * not strobe rings across the screen; and because the fill animation runs
	 * from t=0 regardless, what you see when it fades in is already the true
	 * fraction of the hold elapsed. Delaying the animation instead of just its
	 * opacity would make the ring lie about how much longer to wait.
	 *
	 * It is 104px across with a 5px stroke, and both numbers are about a fingertip
 * rather than about taste: at 56px the finger making the gesture covered the
 * thing describing it, which is the one thing this ring cannot afford to do.
 *
 * Nothing underneath is required. The gesture is the app's, not a widget's,
	 * so it spawns over dead ground too — and when it completes on dead ground
	 * it says so, with an `×` above the ring rather than in it, because the
	 * middle is under a fingertip.
	 *
	 * ## The contract for whatever handles a hold
	 *
	 * On completion this dispatches a cancelable `trophic:hold` on the deepest
	 * element under the point, with `{ x, y }` in `detail`. Call
	 * `preventDefault()` to claim it. Unclaimed holds draw the `×`. That is the
	 * seam the properties panel will attach to: it listens, it claims, it opens
	 * itself at `detail`. Nothing here needs to know it exists.
	 */
	import { LongPress, LONG_PRESS_DELAY } from './longpress';

	/** How long before the ring itself fades in. Longer than a tap, shorter
	 *  than a decision. */
	const APPEAR_MS = 130;

	type Ring = { id: number; x: number; y: number; dead: boolean };

	let ring = $state<Ring | null>(null);
	let seq = 0;

	/** Held across the fire so `contextmenu` can be refused for the moment iOS
	 *  and desktop would otherwise put a menu over the ring. */
	let holding = false;

	function fire(x: number, y: number) {
		holding = false;
		// The deepest element under the finger, which is who gets asked. It may
		// be nothing at all — a hold on the ground is still a hold.
		const target = document.elementFromPoint(x, y) ?? document.body;
		const claimed = !target.dispatchEvent(
			new CustomEvent('trophic:hold', {
				detail: { x, y },
				bubbles: true,
				cancelable: true
			})
		);
		// Claimed: whoever wanted it is opening something, and a refusal mark
		// over the top of it would be a lie. Unclaimed: say so and fade.
		ring = claimed ? null : { id: seq, x, y, dead: true };
		if (!claimed) {
			const mine = seq;
			setTimeout(() => {
				if (ring?.id === mine) ring = null;
			}, 620);
		}
	}

	const press = new LongPress(fire, LONG_PRESS_DELAY);

	function begin(x: number, y: number) {
		holding = true;
		ring = { id: ++seq, x, y, dead: false };
	}

	function cancel() {
		holding = false;
		press.end();
		// Only clear a ring still being filled. A completed one is showing its
		// `×` and owns its own fade.
		if (ring && !ring.dead) ring = null;
	}

	// Touch is the case this is for; mouse is here so the gesture can be worked
	// on at a desk. Both feed the same state machine, so both obey the corpus.
	$effect(() => {
		const points = (e: TouchEvent) =>
			Array.from(e.touches).map((t) => ({ x: t.clientX, y: t.clientY }));

		function touchstart(e: TouchEvent) {
			press.start(points(e));
			// One finger only, matching the state machine: a second finger has
			// already cancelled the press, so it must not leave a ring behind.
			if (e.touches.length === 1) begin(e.touches[0].clientX, e.touches[0].clientY);
			else if (ring && !ring.dead) ring = null;
		}
		function touchmove(e: TouchEvent) {
			press.move(points(e));
			// The ring follows the state machine's verdict rather than
			// re-deciding it: past the slack, the press is dead and so is this.
			const t = e.touches[0];
			if (ring && !ring.dead && t) {
				const drifted = Math.hypot(t.clientX - ring.x, t.clientY - ring.y);
				if (drifted > 10) ring = null;
			}
		}
		function mousedown(e: MouseEvent) {
			if (e.button !== 0) return;
			press.start([{ x: e.clientX, y: e.clientY }]);
			begin(e.clientX, e.clientY);
		}
		function mousemove(e: MouseEvent) {
			if (!holding) return;
			press.move([{ x: e.clientX, y: e.clientY }]);
			if (ring && !ring.dead && Math.hypot(e.clientX - ring.x, e.clientY - ring.y) > 10) {
				ring = null;
			}
		}
		// A hold and a context menu are the same gesture on both platforms, and
		// the menu is the one nobody asked for. Refused only while a hold is
		// live, so an ordinary right-click still works everywhere else.
		function contextmenu(e: MouseEvent) {
			if (holding) e.preventDefault();
		}

		document.addEventListener('touchstart', touchstart, { passive: true, capture: true });
		document.addEventListener('touchmove', touchmove, { passive: true, capture: true });
		document.addEventListener('touchend', cancel, true);
		document.addEventListener('touchcancel', cancel, true);
		document.addEventListener('mousedown', mousedown, true);
		document.addEventListener('mousemove', mousemove, true);
		document.addEventListener('mouseup', cancel, true);
		document.addEventListener('contextmenu', contextmenu, true);
		return () => {
			document.removeEventListener('touchstart', touchstart, true);
			document.removeEventListener('touchmove', touchmove, true);
			document.removeEventListener('touchend', cancel, true);
			document.removeEventListener('touchcancel', cancel, true);
			document.removeEventListener('mousedown', mousedown, true);
			document.removeEventListener('mousemove', mousemove, true);
			document.removeEventListener('mouseup', cancel, true);
			document.removeEventListener('contextmenu', contextmenu, true);
		};
	});

	/** 2πr for r=46. The fill's duration comes from `LONG_PRESS_DELAY` through a
	 *  custom property rather than being written into the stylesheet, so the ring
	 *  cannot say one thing while the state machine waits for another. */
	const CIRCUMFERENCE = 289.03;
</script>

{#if ring}
	{#key ring.id}
		<!-- `fixed` and centred on the touch. It is drawn above the glass — a
		     scanline over the thing telling you the app heard you is the wrong
		     way round — and above the lightbox, because a hold on a photograph
		     is still a hold. -->
		<div
			class="hold-ring"
			class:hold-done={ring.dead}
			style="left:{ring.x}px; top:{ring.y}px; --hold-ms:{LONG_PRESS_DELAY}ms; --hold-appear:{APPEAR_MS}ms"
			aria-hidden="true"
		>
			<svg width="104" height="104" viewBox="0 0 104 104">
				<circle
					cx="52"
					cy="52"
					r="46"
					fill="none"
					stroke="rgba(255, 255, 255, 0.16)"
					stroke-width="5"
				/>
				<!-- Rotated a quarter turn so the path's own start — three
				     o'clock, clockwise — begins at six instead. -->
				<circle
					class="hold-arc"
					cx="52"
					cy="52"
					r="46"
					fill="none"
					stroke="var(--color-accent)"
					stroke-width="5"
					stroke-linecap="round"
					stroke-dasharray={CIRCUMFERENCE}
					stroke-dashoffset={ring.dead ? 0 : CIRCUMFERENCE}
				/>
			</svg>

			{#if ring.dead}
				<!-- Above the ring, not in it: the middle is under a fingertip. -->
				<span class="hold-null">×</span>
			{/if}
		</div>
	{/key}
{/if}

<style>
	.hold-ring {
		position: fixed;
		z-index: 9600;
		width: 104px;
		height: 104px;
		margin: -52px 0 0 -52px;
		pointer-events: none;
		opacity: 0;
		animation: hold-appear 120ms ease-out var(--hold-appear, 130ms) forwards;
	}

	/* The fill runs from the touch, so the fraction showing when the ring fades
	   in is the fraction of the hold already spent. */
	.hold-arc {
		transform: rotate(90deg);
		transform-origin: 52px 52px;
		animation: hold-fill var(--hold-ms, 500ms) linear forwards;
	}

	/* Completed. The ring stops filling, brightens for a moment and goes. */
	.hold-done {
		animation: hold-leave 620ms ease-out forwards;
	}
	.hold-done .hold-arc {
		animation: none;
	}

	.hold-null {
		position: absolute;
		bottom: 100%;
		left: 50%;
		transform: translate(-50%, -4px);
		font-size: 19px;
		line-height: 1;
		color: var(--color-accent);
		animation: hold-leave 620ms ease-out forwards;
	}

	@keyframes hold-appear {
		to {
			opacity: 1;
		}
	}

	@keyframes hold-fill {
		to {
			stroke-dashoffset: 0;
		}
	}

	@keyframes hold-leave {
		0% {
			opacity: 1;
		}
		30% {
			opacity: 1;
		}
		100% {
			opacity: 0;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.hold-ring,
		.hold-arc,
		.hold-null {
			animation-duration: 0.01ms;
		}
	}
</style>
