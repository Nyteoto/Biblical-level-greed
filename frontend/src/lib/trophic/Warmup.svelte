<script lang="ts">
	/**
	 * The boot sequence, then the tube coming on. Once per launch.
	 *
	 * ## How the app knows it was restarted
	 *
	 * `sessionStorage`. It is emptied when the tab or the installed app is
	 * actually closed and reopened — including the case that prompted this,
	 * clearing the app off the multitasking screen and tapping it again — and it
	 * survives everything that is *not* a restart: client-side navigation between
	 * screens, the Log bouncing you into an album, backgrounding the app and
	 * coming back. That is precisely the line this wants to be on, and
	 * `lastAlbum` reads the same signal for the same reason.
	 *
	 * Two things it deliberately does not do. It does not fire when the app is
	 * merely backgrounded — `visibilitychange` would, and a splash every time you
	 * check a message is an app that thinks its own launch is an event you wanted
	 * to attend. And it does not fire on a manual reload, because a reload keeps
	 * the session; `performance.getEntriesByType` reports the navigation type and
	 * would be the thing to read if that ever needs to change.
	 *
	 * ## Two beats, and what each is for
	 *
	 * **The boot screen** is theatre and is meant to be. Nothing is loading — the
	 * shell is static files off localhost — so this is not a progress indicator
	 * and would be a lie if it claimed to be one. It is the machine introducing
	 * itself, which is a thing a green tube is entitled to do, and it is why the
	 * lines name the parts this app actually has rather than inventing a number
	 * to count up. Theatre may be theatrical; it may not be false.
	 *
	 * **The strike** is the transition out of it: a CRT lands a bright horizontal
	 * line and the picture opens from it. That beat is doing real work — it is
	 * what makes the app *arrive* rather than replace the boot screen — so it is
	 * the one that must not be cut.
	 *
	 * Together they are under two seconds, which is the budget for something you
	 * see every time you open the app and cannot skip. The numbers live in one
	 * place below and the stylesheet reads them, so the two halves cannot drift.
	 */
	const BOOT_MS = 1200;
	const STRIKE_MS = 780;

	/** The parts of the app, named honestly. `ok` is a claim about existence,
	 *  not about health — nothing here is checked, and nothing here pretends to
	 *  have been. */
	const LINES: [string, string][] = [
		['log', 'ok'],
		['index', 'ok'],
		['media', 'ok'],
		['tube', 'warm']
	];

	const KEY = 'launched';

	let running = $state(false);

	$effect(() => {
		try {
			if (sessionStorage.getItem(KEY) === '1') return;
			sessionStorage.setItem(KEY, '1');
		} catch {
			// No storage: show it, once, and accept that a reload shows it again.
			// The failure mode of a warm-up is that you see a warm-up.
		}
		running = true;
		const done = setTimeout(() => (running = false), BOOT_MS + STRIKE_MS);
		return () => clearTimeout(done);
	});
</script>

{#if running}
	<div
		class="warmup"
		style="--boot:{BOOT_MS}ms; --strike:{STRIKE_MS}ms; --total:{BOOT_MS + STRIKE_MS}ms"
		aria-hidden="true"
	>
		<div class="warmup-boot">
			<span class="warmup-mark">TROPHIC</span>
			<span class="warmup-sub">capture system</span>

			<ul class="warmup-lines">
				{#each LINES as [part, state], i (part)}
					<!-- Staggered by index rather than by a timer: four elements, four
					     delays, and nothing to tear down if the app is closed mid-boot. -->
					<li style="animation-delay:{120 + i * 150}ms">
						<span class="warmup-part">{part}</span>
						<span class="warmup-dots"></span>
						<span class="warmup-state">{state}</span>
					</li>
				{/each}
			</ul>

			<span class="warmup-bar"></span>
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
		width: min(320px, 72vw);
		flex-direction: column;
		/* Out before the strike, so the line lands on an empty screen rather than
		   over the top of the words. */
		animation: warmup-boot-out 180ms ease-in forwards;
		animation-delay: calc(var(--boot) - 180ms);
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
		animation: warmup-in 160ms ease-out forwards;
	}

	.warmup-part {
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

	/* Fills across the boot, and is the only thing here shaped like progress.
	   It measures the animation, which is the one thing it can measure honestly. */
	.warmup-bar {
		height: 2px;
		border-radius: 2px;
		background: var(--color-accent);
		transform-origin: left;
		transform: scaleX(0);
		box-shadow: 0 0 10px rgba(79, 255, 159, 0.4);
		animation: warmup-fill var(--boot) ease-out forwards;
	}

	/* The strike. Out from the centre as a hairline, then the picture opens from
	   it: the line scales up and fades as the ground beneath it goes.
	   `transform` and `opacity` only, so the whole thing composites. */
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

	@keyframes warmup-fill {
		to {
			transform: scaleX(1);
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
		22% {
			transform: scaleX(1) scaleY(1);
			opacity: 1;
		}
		55% {
			transform: scaleX(1) scaleY(60);
			opacity: 0.22;
		}
		100% {
			transform: scaleX(1) scaleY(150);
			opacity: 0;
		}
	}

	/* Opaque through the boot and most of the strike, then gone. The percentages
	   are of the total, which is why they are not round numbers. */
	@keyframes warmup-clear {
		0%,
		78% {
			opacity: 1;
		}
		100% {
			opacity: 0;
		}
	}

	/* Reduced motion gets the beat without the geometry: the screen is covered,
	   the machine says its name, then it is not. */
	@media (prefers-reduced-motion: reduce) {
		.warmup-line,
		.warmup-bar {
			display: none;
		}
		.warmup-boot {
			animation-delay: 400ms;
		}
	}
</style>
