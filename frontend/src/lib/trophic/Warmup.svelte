<script lang="ts">
	/**
	 * The boot sequence, then the tube coming on. Once per launch.
	 *
	 * ## How the app knows it was restarted
	 *
	 * `sessionStorage`. It is emptied when the tab or the installed app is
	 * actually closed and reopened — including clearing the app off the
	 * multitasking screen and tapping it again — and it survives everything that
	 * is *not* a restart: navigation between screens, the Log bouncing you into
	 * an album, backgrounding and coming back. `lastAlbum` reads the same signal
	 * for the same reason.
	 *
	 * It deliberately does not fire on backgrounding — `visibilitychange` would,
	 * and a splash every time you check a message is an app that thinks its own
	 * launch is an event you wanted to attend — nor on a manual reload, which
	 * keeps the session.
	 *
	 * ## Two beats
	 *
	 * **The boot screen** is theatre and is built to be honest about it. Nothing
	 * is loading, so a bar claiming to measure work would be a lie about work
	 * that is not happening. What it reads out instead is *true*: real module
	 * names from this repo and real media filenames from the log, shuffled fresh
	 * every launch. Filenames only — `CLAUDE.md` allows listing them and forbids
	 * opening them, and nothing here opens anything.
	 *
	 * Three things are randomised per boot so no two launches read alike: which
	 * lines appear and in what order, where the bar's segments land, and when the
	 * tube flickers. The flicker is driven from JS rather than a keyframe because
	 * CSS cannot roll dice — a fixed flicker animation is a rhythm, and a rhythm
	 * is the one thing a failing tube does not have.
	 *
	 * **The strike** is the transition out: a CRT lands a bright line and the
	 * picture opens from it. It is the beat doing real work — it makes the app
	 * *arrive* rather than replace the boot screen — and it is deliberately
	 * shorter than the boot, because it is the part you are waiting through.
	 */
	import { EXPECTED_API } from '$lib/api';
	import { getEntries } from './api';
	import { bootLines, bootSegments, type BootLine } from './boot';

	const BOOT_MS = 1200;
	const STRIKE_MS = 520;
	const ROWS = 5;

	const KEY = 'launched';

	let running = $state(false);
	let lines = $state<BootLine[]>([]);
	let fill = $state(0);
	/** The tube's own unsteadiness. 1 is a healthy screen. */
	let flicker = $state(1);

	$effect(() => {
		try {
			if (sessionStorage.getItem(KEY) === '1') return;
			sessionStorage.setItem(KEY, '1');
		} catch {
			// No storage: show it, once, and accept that a reload shows it again.
			// The failure mode of a warm-up is that you see a warm-up.
		}
		running = true;

		// The lines start with what is knowable without asking anyone — module
		// names — and the user's own media is spliced in if the log answers in
		// time. It usually does; it is localhost. If it does not, the boot reads
		// exactly as well, which is the requirement for putting a fetch here at
		// all.
		lines = bootLines([], ROWS);
		getEntries({ limit: 12 })
			.then((r) => {
				const refs = r.entries.flatMap((e) => e.media ?? []);
				if (refs.length && running) lines = bootLines(refs, ROWS);
			})
			.catch(() => {
				/* modules alone */
			});

		const timers: ReturnType<typeof setTimeout>[] = [];

		// The bar, in lumps. Each stop lands at its own moment and then nothing
		// happens for a while, which is what makes the next one look like
		// something completing.
		const stops = bootSegments();
		stops.forEach((stop, i) => {
			const at = Math.round((BOOT_MS * (i + 1)) / stops.length - 40 - Math.random() * 90);
			timers.push(setTimeout(() => (fill = stop), Math.max(60, at)));
		});

		// Flicker: a handful of random dips, each a couple of frames long. Not a
		// loop — a tube settling does it less as it warms, so the dips are drawn
		// from the first two thirds of the boot.
		const dips = 3 + Math.floor(Math.random() * 4);
		for (let i = 0; i < dips; i++) {
			const at = Math.random() * BOOT_MS * 0.66;
			const depth = 0.35 + Math.random() * 0.45;
			timers.push(setTimeout(() => (flicker = depth), at));
			timers.push(setTimeout(() => (flicker = 1), at + 30 + Math.random() * 70));
		}

		timers.push(setTimeout(() => (running = false), BOOT_MS + STRIKE_MS));
		return () => timers.forEach(clearTimeout);
	});
</script>

{#if running}
	<div
		class="warmup"
		style="--boot:{BOOT_MS}ms; --strike:{STRIKE_MS}ms; --total:{BOOT_MS + STRIKE_MS}ms"
		aria-hidden="true"
	>
		<div class="warmup-boot" style="opacity:{flicker}">
			<span class="warmup-mark">TROPHIC</span>
			<span class="warmup-sub">P.G.S version {EXPECTED_API}</span>

			<ul class="warmup-lines">
				{#each lines as line, i (line.part)}
					<!-- Keyed on the name, so a line replaced when the media arrives
					     re-runs its own reveal rather than snapping into place. -->
					<li style="animation-delay:{60 + i * 110}ms">
						<span class="warmup-part">{line.part}</span>
						<span class="warmup-dots"></span>
						<span class="warmup-state">{line.state}</span>
					</li>
				{/each}
			</ul>

			<span class="warmup-bar">
				<!-- No transition: a segment is a jump, and easing one would put the
				     ramp back that the segments exist to remove. -->
				<span class="warmup-bar-fill" style="transform:scaleX({fill})"></span>
			</span>
		</div>

		<span class="warmup-line"></span>
	</div>
{/if}

<style>
	/* The ground, then nothing. Removed from the document when it is finished
	   rather than left at zero opacity: it covers the whole screen. */
	.warmup {
		position: fixed;
		inset: 0;
		z-index: 9800;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--color-ground);
		pointer-events: none;
		animation: warmup-clear var(--total) linear forwards;
	}

	.warmup-boot {
		display: flex;
		width: min(340px, 74vw);
		flex-direction: column;
		/* The flicker is an inline opacity; this is the only thing that moves it
		   otherwise, and it is fast enough that a dip mid-fade still reads. */
		transition: opacity 40ms linear;
		animation: warmup-boot-out 160ms ease-in forwards;
		animation-delay: calc(var(--boot) - 160ms);
	}

	.warmup-mark {
		font-size: 22px;
		font-weight: 800;
		letter-spacing: 0.3em;
		color: var(--color-accent);
		text-shadow: 0 0 18px rgba(79, 255, 159, 0.45);
	}

	.warmup-sub {
		margin-top: 2px;
		font-size: 11px;
		letter-spacing: 0.22em;
		text-transform: uppercase;
		color: var(--color-neutral-600);
	}

	.warmup-lines {
		margin: 22px 0 18px;
		display: flex;
		flex-direction: column;
		gap: 5px;
		font-size: 12px;
	}

	.warmup-lines li {
		display: flex;
		align-items: baseline;
		gap: 8px;
		opacity: 0;
		animation: warmup-in 140ms ease-out forwards;
	}

	.warmup-part {
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		max-width: 62%;
		color: var(--color-neutral-700);
	}

	/* The leader, drawn rather than typed, so it fills whatever room is left
	   between a short name and its state. */
	.warmup-dots {
		flex: 1;
		height: 1px;
		align-self: center;
		background-image: linear-gradient(
			to right,
			var(--color-neutral-400) 0 2px,
			transparent 2px 5px
		);
		background-size: 5px 1px;
	}

	.warmup-state {
		color: var(--color-accent);
	}

	.warmup-bar {
		display: block;
		height: 2px;
		overflow: hidden;
		border-radius: 2px;
		background: var(--color-neutral-300);
	}

	.warmup-bar-fill {
		display: block;
		height: 100%;
		width: 100%;
		transform-origin: left;
		transform: scaleX(0);
		background: var(--color-accent);
		box-shadow: 0 0 10px rgba(79, 255, 159, 0.4);
	}

	/* The strike. Out from the centre as a hairline, then the picture opens from
	   it. `transform` and `opacity` only, so the whole thing composites. */
	.warmup-line {
		position: absolute;
		width: 62%;
		height: 2px;
		border-radius: 2px;
		background: var(--color-accent);
		box-shadow: 0 0 18px 2px rgba(79, 255, 159, 0.55);
		transform: scaleX(0);
		opacity: 0;
		animation: warmup-strike var(--strike) ease-out forwards;
		animation-delay: var(--boot);
	}

	@keyframes warmup-in {
		to {
			opacity: 1;
		}
	}

	@keyframes warmup-boot-out {
		to {
			opacity: 0;
		}
	}

	@keyframes warmup-strike {
		0% {
			transform: scaleX(0) scaleY(1);
			opacity: 1;
		}
		26% {
			transform: scaleX(1) scaleY(1);
			opacity: 1;
		}
		58% {
			transform: scaleX(1) scaleY(60);
			opacity: 0.22;
		}
		100% {
			transform: scaleX(1) scaleY(150);
			opacity: 0;
		}
	}

	/* Opaque through the boot and most of the strike, then gone. The percentage
	   is of the total, which is why it is not a round number. */
	@keyframes warmup-clear {
		0%,
		82% {
			opacity: 1;
		}
		100% {
			opacity: 0;
		}
	}

	/* Reduced motion gets the beat without the geometry or the flicker. */
	@media (prefers-reduced-motion: reduce) {
		.warmup-line {
			display: none;
		}
		.warmup-boot {
			animation-delay: 400ms;
		}
	}
</style>
