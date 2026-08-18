<script lang="ts">
	/**
	 * The tube coming on. Once per launch, and not once per navigation.
	 *
	 * ## How the app knows it was restarted
	 *
	 * `sessionStorage`. It is emptied when the tab or the installed app is
	 * actually closed and reopened — including the case that prompted this,
	 * clearing the app off the multitasking screen and tapping it again — and it
	 * survives everything that is *not* a restart: client-side navigation between
	 * screens, the Log bouncing you into an album, backgrounding the app and
	 * coming back to it. That is precisely the line this animation wants to
	 * be on. `lastAlbum` reads the same signal for the same reason.
	 *
	 * Two things it deliberately does not do. It does not fire when the app is
	 * merely backgrounded — `visibilitychange` would, and a splash every time you
	 * check a message is an app that thinks its own launch is an event you wanted
	 * to attend. And it does not fire on a manual reload, because a reload keeps
	 * the session; if that ever needs to change, `performance.getEntriesByType`
	 * reports the navigation type and would be the thing to read.
	 *
	 * ## Why this animation and not a spinner
	 *
	 * A spinner says "wait". There is nothing to wait for — the shell is static
	 * files off localhost — so this is not a loading state, it is the screen
	 * turning on. A CRT strikes a bright horizontal line first and the picture
	 * opens out of it, which is a thing this app can honestly claim to be, and
	 * it is over in 700ms whether or not anything has finished loading.
	 *
	 * It sits above the glass and above the lightbox, because it is the moment
	 * before the app rather than a layer on top of it.
	 */
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
		const done = setTimeout(() => (running = false), 780);
		return () => clearTimeout(done);
	});
</script>

{#if running}
	<div class="warmup" aria-hidden="true">
		<span class="warmup-line"></span>
	</div>
{/if}

<style>
	/* The ground, then nothing. It is removed from the document when it is
	   finished rather than left at zero opacity — it covers the whole screen and
	   it is over in under a second. */
	.warmup {
		position: fixed;
		inset: 0;
		z-index: 9800;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--color-ground);
		pointer-events: none;
		animation: warmup-clear 780ms ease-out forwards;
	}

	/* The strike. Out from the centre as a hairline, then the picture opens from
	   it — the line scales up vertically and fades as the ground beneath it goes.
	   `transform` and `opacity` only, so the whole thing composites. */
	.warmup-line {
		width: 62%;
		height: 2px;
		border-radius: 2px;
		background: var(--color-accent);
		box-shadow: 0 0 18px 2px rgba(79, 255, 159, 0.55);
		transform: scaleX(0);
		animation: warmup-strike 780ms ease-out forwards;
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

	@keyframes warmup-clear {
		0%,
		48% {
			opacity: 1;
		}
		100% {
			opacity: 0;
		}
	}

	/* Reduced motion gets the same beat without the geometry: the screen is
	   covered, then it is not. */
	@media (prefers-reduced-motion: reduce) {
		.warmup {
			animation-duration: 260ms;
		}
		.warmup-line {
			display: none;
		}
	}
</style>
