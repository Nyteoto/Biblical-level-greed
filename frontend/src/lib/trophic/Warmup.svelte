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
	import { bootHint, bootLine, bootPool, bootSegments, type BootLine } from './boot';

	const BOOT_MS = 3200;
	const STRIKE_MS = 520;
	/** How many lines stand on screen at once. The log rolls: a new one arrives
	 *  every few hundred milliseconds and the oldest leaves, which is what fills
	 *  three seconds without the screen going still. */
	const ROWS = 6;

	const KEY = 'launched';

	let running = $state(false);
	let lines = $state<BootLine[]>([]);
	let fill = $state(0);
	/** The tube's own unsteadiness. 1 is a healthy screen. */
	let flicker = $state(1);
	/** One true thing about the app, drawn once per boot. */
	const hint = bootHint();

	$effect(() => {
		try {
			if (sessionStorage.getItem(KEY) === '1') return;
			sessionStorage.setItem(KEY, '1');
		} catch {
			// No storage: show it, once, and accept that a reload shows it again.
			// The failure mode of a warm-up is that you see a warm-up.
		}
		running = true;

		// The names start with what is knowable without asking anyone — this
		// repo's own parts — and the user's media is folded into the pool when
		// the log answers. It usually does; it is localhost. If it never does,
		// the boot reads exactly as well, which is the condition for putting a
		// fetch here at all.
		let pool = bootPool([]);
		lines = Array.from({ length: 3 }, () => bootLine(pool));
		getEntries({ limit: 12 })
			.then((r) => {
				const refs = r.entries.flatMap((e) => e.media ?? []);
				if (refs.length) pool = bootPool(refs);
			})
			.catch(() => {
				/* this repo's parts alone */
			});

		const timers: ReturnType<typeof setTimeout>[] = [];
		const intervals: ReturnType<typeof setInterval>[] = [];

		// The roll. One more line, the oldest off the top.
		intervals.push(
			setInterval(() => {
				lines = [...lines, bootLine(pool)].slice(-ROWS);
			}, 300)
		);

		// The bar, in lumps. Each stop lands at its own moment and then nothing
		// happens for a while, which is what makes the next one look like
		// something completing.
		const stops = bootSegments();
		stops.forEach((stop, i) => {
			const at = Math.round((BOOT_MS * (i + 1)) / stops.length - 80 - Math.random() * 220);
			timers.push(setTimeout(() => (fill = stop), Math.max(80, at)));
		});

		// The flicker, and the reason it is here rather than in a keyframe: CSS
		// cannot roll dice, and a fixed flicker is a rhythm — which is the one
		// thing a failing tube does not have.
		//
		// Set and cleared with no transition, on purpose. The first attempt eased
		// it over 40ms while the dips themselves were 30ms long, so the opacity
		// never arrived anywhere before being sent back and the effect was
		// invisible. A tube does not ease; it drops and returns.
		const dips = 10 + Math.floor(Math.random() * 8);
		for (let i = 0; i < dips; i++) {
			const at = 80 + Math.random() * (BOOT_MS - 240);
			// Mostly quick brown-outs, occasionally a surge — a run that only ever
			// dims reads as a pulse rather than as an unsteady supply.
			const surge = Math.random() < 0.25;
			const depth = surge ? 1.35 + Math.random() * 0.35 : 0.12 + Math.random() * 0.35;
			const held = 45 + Math.random() * 90;
			timers.push(setTimeout(() => (flicker = depth), at));
			timers.push(setTimeout(() => (flicker = 1), at + held));
		}

		timers.push(setTimeout(() => (running = false), BOOT_MS + STRIKE_MS));
		return () => {
			timers.forEach(clearTimeout);
			intervals.forEach(clearInterval);
		};
	});
</script>

{#if running}
	<div
		class="warmup"
		style="--boot:{BOOT_MS}ms; --strike:{STRIKE_MS}ms; --total:{BOOT_MS + STRIKE_MS}ms"
		aria-hidden="true"
	>
		<!-- `opacity` carries a brown-out and `brightness` a surge: opacity cannot
		     exceed 1, and a tube that only ever dims reads as a fade rather than
		     as an unsteady supply. -->
		<div
			class="warmup-boot"
			style="opacity:{Math.min(1, flicker)}; filter:brightness({Math.max(1, flicker)})"
		>
			<!-- Above the wordmark, because it is the one line here worth reading
			     and the mark is the one thing that does not change. -->
			<span class="warmup-hint">Hint: {hint}</span>
			<span class="warmup-mark">TROPHIC</span>
			<span class="warmup-sub">P.G.S version {EXPECTED_API}</span>

			<ul class="warmup-lines">
				{#each lines as line (line.id)}
					<!-- Keyed on an id, not the name: the log rolls, and over three
					     seconds the same file can legitimately come round twice. Each
					     arrival is a new element and plays its own reveal. -->
					<li>
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
		/* No transition. The flicker is set and cleared outright — easing it is
		   exactly what made the first version invisible. */
		animation: warmup-boot-out 160ms ease-in forwards;
		animation-delay: calc(var(--boot) - 160ms);
	}

	.warmup-hint {
		margin-bottom: 14px;
		font-size: 11px;
		line-height: 1.5;
		color: var(--color-neutral-700);
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
