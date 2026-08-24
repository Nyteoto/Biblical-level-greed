<script lang="ts">
	/**
	 * Promises kept over promises made, all of history, standing in the corner
	 * of the capture screen.
	 *
	 * Every other figure in this app is a count of something you can go and look
	 * at — entries, media, albums. This one is not a count, it is a *ratio*, and
	 * it is the only number here that says anything about whether the thing you
	 * are doing is working. Ten open todos is a rule the write enforces; `128 /
	 * 147` is the record of what happened to every promise that ever passed
	 * through that rule. It is on the capture screen and nowhere else because
	 * that is where promises are made.
	 *
	 * Which is why it is not a chip. A number that means something different
	 * from every other number on the screen has to *look* different from them,
	 * or it reads as another tally and is skipped. So it is a die-cut sticker
	 * with real depth, sitting off the glass — the one object in the app that is
	 * neither flat against it nor a rectangle.
	 *
	 * The spikes are doing the work a second colour would otherwise have to do.
	 * Everything else here is a rounded-off rectangle in a column of rectangles,
	 * and this app has one hue, so there is no accent left to spend on saying
	 * *this one is different*. A shape can say it instead: a seal is a thing
	 * awarded rather than a thing measured, and nothing else on the screen is
	 * that shape.
	 *
	 * The legend rides the inner perimeter rather than sitting under the figure,
	 * which is what leaves the middle of the sticker to the number alone. See
	 * `tally-face.ts`.
	 *
	 * ## This component owns almost nothing
	 *
	 * The sticker is a three.js scene — `tally-scene.ts` — and everything here
	 * is the app's half of it: what the numbers are, where the pointer is, and
	 * when something has just been kept. Three things go down to the scene
	 * (`aim`, `setFigures`, `pulse`) and nothing comes back.
	 *
	 * The scene is loaded on demand, for two reasons that point the same way:
	 * three.js is by far the largest thing in this bundle and one screen wants
	 * it, and a machine with no WebGL has to be able to fail at exactly one
	 * point and get the flat sticker instead. Both are the same `catch`.
	 *
	 * ## It is also a toy, and that is the whole of what it is
	 *
	 * You can take hold of the sticker and turn it, flick it and watch it spin
	 * down, or tap it and have it wobble. **None of it does anything.** There is
	 * no gesture here that opens a screen, changes a number or writes a line —
	 * it is a thing on your desk that you can push about while you think of what
	 * to type, and it exists because a screen you look at every day should have
	 * one thing on it that is simply pleasant.
	 *
	 * It is worth saying why that is allowed here when this app refuses almost
	 * every ornament: nothing about it is a claim. The rules in CLAUDE.md are
	 * about the app never interpreting, never nagging and never inventing state,
	 * and a spinning sticker does none of those. The figure on it stays exactly
	 * as true whichever way round it is pointing.
	 *
	 * The pointer is not captured for it either. `preventDefault` on the press
	 * means the caret never leaves the capture bar, so you can spin the thing
	 * mid-sentence and keep typing without clicking back — which is the
	 * difference between a toy and an interruption.
	 *
	 * ## The four things it answers to
	 *
	 * **The pointer.** It stands turned toward the middle of the screen already,
	 * and turns further to face wherever the pointer is — until you take hold of
	 * it, at which point the aim becomes the spring it settles back onto. That
	 * is the reason for the depth being real rather than painted: a static drop
	 * shadow reads as 3D until something moves, and then it reads as a sticker.
	 * On a touch screen there is no pointer and the resting angle is the whole
	 * of it, which is why the angle is a resting one and not a reaction.
	 *
	 * **A hand on it.** Drag turns it, a flick spins it, a tap shoves it, and
	 * the harder it is worked the hotter it runs: the print burns brighter, the
	 * cut edge picks up and the halo swells. One number drives all three — see
	 * `heat` in `tally-scene.ts` — because three effects on separate schedules
	 * read as three effects rather than as one object.
	 *
	 * **A promise kept.** `done` goes up and it comes forward at you and
	 * settles. This is the one event in the app that deserves to be celebrated
	 * and had nowhere to be celebrated: ticking a todo in the journal changed a
	 * checkbox and a banner count, both of which look like bookkeeping.
	 *
	 * **A promise made.** `made` goes up and it takes a step back. The mirror of
	 * the other, and quieter than it on purpose.
	 *
	 * ## It does not dim, and that is deliberate
	 *
	 * The header, the syntax keys and the standing banner all fade out four
	 * seconds after the last keystroke — see `dim.svelte.ts` — and this does
	 * not. **Do not "fix" that.** The dim exists so that the screen holds one
	 * thought while a thought is being written, and everything it takes away is
	 * chrome for acting on something *else*: a tab to leave by, a folder to pin,
	 * a strip announcing the next thing owed. This is not one of those. It is
	 * the standing fact the screen is kept for, it is true whether or not you
	 * are mid-sentence, and a record of what you have kept is not an
	 * interruption to writing the next one down.
	 *
	 * It is the only lit thing left once the chrome has gone, which is the exact
	 * argument `dim.svelte.ts` makes against leaving the banner lit. The
	 * difference is what the two say: a banner still up is a queue still waiting
	 * on you, and this is a figure that asks for nothing.
	 *
	 * There is no empty state either. `0 / 0` is what it reads before the first
	 * promise is written, and that is the honest figure rather than a fault — a
	 * tally that appears only once it has something to report is not a standing
	 * one.
	 *
	 * The numbers come from the banner's own read — `made - done` is `open`, the
	 * count the strip above draws — so the two cannot disagree about the same
	 * fold. See `store.banner`.
	 */
	import { banner } from './banner-state.svelte';
	import { FRAME, paintFlat } from './tally-face';
	import type { Tally } from './tally-scene';

	const bar = banner();
	const made = $derived(bar.data?.made ?? 0);
	const done = $derived(bar.data?.done ?? 0);

	/** How big the sticker looks, and how big the canvas around it is. The
	 *  canvas is much the larger of the two, and `FRAME` — which the scene sets
	 *  its camera by — is what decides by how much: a solid that turns and
	 *  advances needs a little room, and the glow behind it needs a lot, because
	 *  anything that reaches the edge of the canvas is cut off square there.
	 *
	 *  `PAD` is the difference, and it is what the corner offsets below are
	 *  struck against, so the *sticker* stays where it is put however much room
	 *  the glow is given. */
	const SIZE = 122;
	const BOX = Math.round(SIZE * FRAME);
	const PAD = (BOX - SIZE) / 2;

	// The angle it sits at with nobody looking, and the difference between a
	// solid and a circle: square-on until the pointer moves is a flat sticker
	// for as long as nobody touches it, and the thickness — the entire reason
	// this is not a chip — would be invisible exactly when it is doing its one
	// job. So it stands turned, like a plaque propped on a desk.
	//
	// Turned toward the middle of the screen and tipped up, because that is
	// where the reader is: this sits in the bottom-left corner, and a face
	// square to the glass down there is a face aimed at nobody.
	const REST_TURN = 22;
	const REST_PITCH = -11;

	// How far the pointer can move it. Kept inside the resting turn so it never
	// crosses square-on and swaps which side its thickness is on — an object
	// does not turn itself inside out when you cross the screen.
	const MAX_TURN = 11;
	const MAX_PITCH = 8;

	let canvas = $state<HTMLCanvasElement | null>(null);
	/** Set when the scene could not be had — no WebGL, or the chunk failed to
	 *  load. The same canvas then gets the flat sticker painted into it. */
	let flat = $state(false);

	let tally: Tally | null = null;

	/** Not `$state`: read and written inside the effect that watches the pair,
	 *  and a rune here would make that effect its own dependency. */
	let seen: { made: number; done: number } | null = null;

	// ── The scene ────────────────────────────────────────────────────────────

	$effect(() => {
		let living = true;
		import('./tally-scene')
			.then(({ mount }) => {
				if (!living || !canvas) return;
				tally = mount(canvas, { done, made });
				tally.aim(REST_TURN, REST_PITCH);
			})
			.catch(() => {
				// One catch for both failures, because the answer to both is the
				// same picture. Nothing is reported: a badge that cannot be a
				// solid is still a badge, and there is nothing here for the user
				// to do about it.
				if (living) flat = true;
			});
		return () => {
			living = false;
			tally?.dispose();
			tally = null;
		};
	});

	/** The flat one, drawn once per change rather than once per frame. */
	$effect(() => {
		if (!flat || !canvas) return;
		const ctx = canvas.getContext('2d');
		if (ctx) paintFlat(ctx, { done, made }, SIZE);
	});

	$effect(() => {
		const now = { made, done };
		// Painted first and unconditionally, *before* the guard below. The face
		// is a texture rather than markup, so it is only ever as current as the
		// last call: the scene is mounted with whatever the banner had at the
		// time, which on a cold load is nothing, and if this were skipped on the
		// read that finally brings the numbers in the sticker would read `0 / 0`
		// until one of them next changed. Cheap to repaint, and it happens twice
		// a session.
		tally?.setFigures(now);

		// The first read is not an event. The banner arrives a moment after the
		// screen does, and a badge that celebrates every page load is a badge
		// nobody believes the third time.
		if (seen === null) {
			if (bar.data) seen = now;
			return;
		}
		const kept = now.done > seen.done;
		const written = now.made > seen.made;
		seen = now;
		// Kept wins if somehow both moved at once — the good half of the news is
		// the half worth showing.
		if (kept) tally?.pulse('kept');
		else if (written) tally?.pulse('made');
	});

	// ── The hand ─────────────────────────────────────────────────────────────

	/** Where the pointer was last, and how far it has come since it went down.
	 *  The second is what tells a tap from a drag on the way up. */
	let last: { x: number; y: number } | null = null;
	let travelled = 0;

	function grab(event: PointerEvent) {
		if (!tally) return;
		// The caret stays where it is. Without this the press blurs the capture
		// bar, and a toy you cannot touch mid-sentence without losing your place
		// is not a toy, it is an interruption.
		event.preventDefault();
		// Capture so a fast drag off the corner of the screen keeps turning it
		// rather than stopping at the canvas edge. It throws if the pointer is
		// already gone, which costs nothing here: the drag simply ends at the
		// edge instead.
		try {
			(event.currentTarget as HTMLElement).setPointerCapture(event.pointerId);
		} catch {
			/* nothing to hold on to */
		}
		last = { x: event.clientX, y: event.clientY };
		travelled = 0;
		tally.grab();
	}

	function turn(event: PointerEvent) {
		if (!last || !tally) return;
		const dx = event.clientX - last.x;
		const dy = event.clientY - last.y;
		last = { x: event.clientX, y: event.clientY };
		travelled += Math.abs(dx) + Math.abs(dy);
		tally.drag(dx, dy);
	}

	function letGo(event: PointerEvent) {
		if (!last || !tally) return;
		last = null;
		tally.release();
		// Four pixels of slack, because a tap on a touch screen is never
		// perfectly still and a tap that turned into a one-degree drag should
		// still read as a tap.
		if (travelled < 4) tally.nudge();
		try {
			(event.currentTarget as HTMLElement).releasePointerCapture(event.pointerId);
		} catch {
			/* it was never held */
		}
	}

	// ── The pointer ──────────────────────────────────────────────────────────

	/**
	 * Turn to face the pointer.
	 *
	 * Coalesced onto one animation frame, because `mousemove` fires faster than
	 * anything downstream draws and every extra call would only be thrown away.
	 * Only on a machine with a pointer to follow: on the iPad this app is
	 * actually read on there is nothing to face, and the resting angle and the
	 * drift are the whole effect.
	 */
	$effect(() => {
		if (!window.matchMedia('(hover: hover)').matches) return;
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

		let frame = 0;
		let point: { x: number; y: number } | null = null;

		function settle() {
			frame = 0;
			if (!canvas || !point) return;
			const box = canvas.getBoundingClientRect();
			const cx = box.left + box.width / 2;
			const cy = box.top + box.height / 2;
			// Normalised against half the viewport, so the turn is a direction
			// rather than a distance: the pointer at the far edge is fully turned
			// on whatever machine this is being read on.
			const dx = (point.x - cx) / (window.innerWidth / 2);
			const dy = (point.y - cy) / (window.innerHeight / 2);
			const clamp = (v: number) => Math.max(-1, Math.min(1, v));
			tally?.aim(REST_TURN + clamp(dx) * MAX_TURN, REST_PITCH + clamp(dy) * MAX_PITCH);
		}

		function move(event: MouseEvent) {
			// A hand on the sticker outranks the pointer following it: while it
			// is held the aim is only the angle it will settle back onto, and
			// updating it under your fingers would move the target you are
			// about to be handed back to.
			if (last) return;
			point = { x: event.clientX, y: event.clientY };
			if (!frame) frame = requestAnimationFrame(settle);
		}

		// Off the window entirely: it faces front again rather than holding the
		// last angle it was left at, which reads as stuck.
		function leave() {
			point = null;
			tally?.aim(REST_TURN, REST_PITCH);
		}

		window.addEventListener('mousemove', move);
		document.addEventListener('mouseleave', leave);
		return () => {
			if (frame) cancelAnimationFrame(frame);
			window.removeEventListener('mousemove', move);
			document.removeEventListener('mouseleave', leave);
		};
	});
</script>

<!-- No `ui-dim`, and no condition on there being anything to report: this is
     the one thing on the capture screen that stands. See the note at the top. -->
<div
	class="tally"
	style="--tally-pad:{PAD}px"
	role="img"
	aria-label="all time todos: {done} of {made} done"
	title="all time todos: {done} of {made} done"
>
	<!-- The drift is CSS on the wrapper rather than a rotation inside the scene,
	     and that is the whole performance story: this is composited, so the
	     sticker can idle for an hour without the renderer drawing a frame. -->
	<div class="tally-float">
		<canvas
			bind:this={canvas}
			class="tally-canvas"
			class:flat
			width={flat ? SIZE : BOX}
			height={flat ? SIZE : BOX}
			style="width:{flat ? SIZE : BOX}px;height:{flat ? SIZE : BOX}px"
			onpointerdown={grab}
			onpointermove={turn}
			onpointerup={letGo}
			onpointercancel={letGo}
		></canvas>
	</div>
</div>

<style>
	/* The corner it stands in. The offsets are the *sticker's* own — its edge
	   sits 13px off the bottom and 34px in from the left — with the canvas's
	   padding taken back off, so the glow's margin hangs off the edge of the
	   screen instead of pushing the badge inward. */
	.tally {
		position: absolute;
		bottom: calc(13px - var(--tally-pad));
		left: calc(15px - var(--tally-pad));
		pointer-events: none;
		user-select: none;
	}

	@media (min-width: 640px) {
		.tally {
			left: calc(34px - var(--tally-pad));
		}
	}

	.tally-float {
		animation: tally-float 7.5s ease-in-out infinite;
	}

	/* Nothing here takes the pointer except the sticker itself, and it only
	   takes one so the tooltip can be got at — the title on the wrapper is the
	   only place "all time" is written out in full. */
	.tally-canvas {
		display: block;
		pointer-events: auto;
		cursor: grab;
		/* The gestures are this element's own. Without this a drag on a touch
		   screen scrolls the page out from under the sticker. */
		touch-action: none;
	}

	.tally-canvas:active {
		cursor: grabbing;
	}

	/* Nothing to take hold of when it is a picture rather than a solid. */
	.tally-canvas.flat {
		cursor: default;
	}

	/* A slow, shallow drift. It is a floating object, not a bobbing one: four
	   pixels of travel and under a degree of roll, which is enough to stop it
	   reading as printed on the glass and not enough to be watched. */
	@keyframes tally-float {
		0%,
		100% {
			transform: translate3d(0, 0, 0) rotate(0deg);
		}
		50% {
			transform: translate3d(0, -4px, 0) rotate(-0.7deg);
		}
	}

	/* The blanket rule in `trophic.css` flattens animation durations; the drift
	   is switched off outright instead, because an animation that ends leaves
	   the sticker wherever its last frame put it. */
	@media (prefers-reduced-motion: reduce) {
		.tally-float {
			animation: none;
		}
	}
</style>
