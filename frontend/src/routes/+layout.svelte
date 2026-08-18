<script lang="ts">
	import '../app.css';
	// Trophic's animation vocabulary, and the `.trophic` scope below that its
	// reduced-motion rule keys off. It sits at the root now rather than on the
	// capture route group: Settings and the Manual are Trophic's screens too,
	// and they were the two that quietly opted out of it.
	import '$lib/trophic/trophic.css';
	import UploadBar from '$lib/trophic/UploadBar.svelte';
	import HoldRing from '$lib/trophic/HoldRing.svelte';
	import { monitor } from '$lib/trophic/monitor.svelte';

	let { children } = $props();

	// The monitor's six numbers, read back from this machine. Until this runs
	// the screen is lit by the defaults `:root` carries in `app.css`, which are
	// the same numbers — so nothing flashes.
	$effect(() => {
		monitor.hydrate();
	});

	// The only place the settings reach the glass. Six custom properties onto
	// the document element and nothing else: the layers below and the rules in
	// `app.css` are unchanged and unaware, which is the same separation that
	// lets the app be rewritten without touching the treatment.
	$effect(() => {
		const root = document.documentElement.style;
		for (const [prop, value] of Object.entries(monitor.vars)) root.setProperty(prop, value);
	});


	/**
	 * Press feedback, for everything, from one place.
	 *
	 * A per-component `pressed` flag is how the syntax keys already do this, and
	 * doing that everywhere else would be forty copies of the same three lines —
	 * so this listens once, at the document, and the styling is one class in
	 * `trophic.css`. Components stay unaware of it, which is the same separation
	 * the glass has.
	 *
	 * `pointerdown` and not `click`: the point is to answer the finger, and a
	 * click arrives on release. It also fires for presses that do nothing at all
	 * — a tab you are already on, a disabled-looking control, a link mid-fetch —
	 * which is the whole request. A control that ignores you and a control that
	 * has nothing to do look identical otherwise.
	 *
	 * Capture phase, so a component calling `stopPropagation` on its own
	 * handler — the lightbox does, on everything that is not the backdrop —
	 * cannot silently opt out of being responsive.
	 */
	const PRESSABLE = 'button, a[href], [role="button"], [role="switch"], summary';

	$effect(() => {
		function press(event: PointerEvent) {
			const from = event.target as Element | null;
			// `label` is not in the selector because most labels are not pressable;
			// the one kind that is wraps its own input, which is how the capture
			// bar's attach button is built.
			const el = (from?.closest?.(PRESSABLE) ??
				from?.closest?.('label:has(input)')) as HTMLElement | null;
			if (!el) return;

			// Restart rather than ignore a second press inside the first flash:
			// a control tapped twice should answer twice. Removing the class and
			// reading a layout property forces the animation to begin again.
			el.classList.remove('tap-flash', 'tap-flash-anchor');
			void el.offsetWidth;
			if (getComputedStyle(el).position === 'static') el.classList.add('tap-flash-anchor');
			el.classList.add('tap-flash');
		}

		function done(event: AnimationEvent) {
			if (event.animationName !== 'tap-flash') return;
			(event.target as HTMLElement).classList?.remove('tap-flash', 'tap-flash-anchor');
		}

		document.addEventListener('pointerdown', press, true);
		document.addEventListener('animationend', done, true);
		return () => {
			document.removeEventListener('pointerdown', press, true);
			document.removeEventListener('animationend', done, true);
		};
	});

	// The shell is now almost nothing: a ground, an upload bar, and the page.
	//
	// The tab bar that used to live here is gone, and so is the XP meter beside
	// it. Both belonged to the arrangement where the tech tree was the app and
	// capture was a fifth tab; capture is the app, the tree's screens are
	// hidden, and there is no XP economy on screen to meter. Navigation is one
	// white pill (`TabPill.svelte`) that each screen places for itself, because
	// it does not sit in the same corner on all three — see that file.
</script>

<svelte:head>
	<title>Trophic</title>
</svelte:head>

<!-- `data-shell-header` is what claims the status-bar inset on an installed
     phone. It is an attribute rather than a `header` selector because the Log's
     day headings are `header` elements too, and every one of them was quietly
     padding itself by the height of the notch. -->

<!-- The hold gesture, over everything and belonging to nothing. Mounted here
     for the same reason the glass is: it is the app's, not a screen's. -->
<HoldRing />

<div data-shell-header class="trophic flex min-h-dvh flex-col">
	<!-- Above the page: an upload outlives the screen that started it, so its
	     progress belongs to the shell rather than to the capture bar.
	     It is `sticky`, and it stays *outside* the curve for that reason — a
	     filtered ancestor becomes the containing block for anything positioned
	     inside it, which would anchor this to the page instead of the viewport. -->
	<UploadBar />

	<!-- Nothing here is filtered. Everything the glass does is done by the
	     layers below, which are flat, fixed and know nothing about what they are
	     over — see `app.css` for what the curve cost before it became one of
	     them. -->
	<main class="flex flex-1 flex-col">
		{@render children()}
	</main>
</div>

<!-- The glass. Four full-screen layers and six small ones, over everything, `pointer-events: none`, entirely
     unaware of the app underneath — which is what lets the app be rewritten
     without any of this having to move.

     Order is paint order, and it is the one thing here that is not arbitrary:
     the sheen sits under the grain and the scanlines so the lines run *across*
     the highlight the way they would on real glass, and the bezel is last
     because it is the edge of the picture and nothing is outside that.

     Four full-screen layers and not five: each is a viewport-sized paint on
     every frame, and that count is the frame budget. Everything added to
     suggest the curve is either folded into a layer that already existed or is
     a few hundred pixels big. See `app.css` for what the tidier versions cost.

     They come out of the document together when the monitor is off, rather than
     staying at zero opacity: four full-viewport painted layers are a real cost
     for something nobody can see, and the switch means the tube, not the
     brightness. -->
{#if monitor.on}
	<div class="crt crt-glow"></div>
	<div class="crt crt-grain"></div>
	<div class="crt crt-scan"></div>
	<div class="crt crt-vignette"></div>
	<!-- The edge of the picture. Six small elements rather than a seventh
	     full-viewport one — see `app.css` for the 12ms that cost. -->
	<div class="crt-corner crt-corner-tl"></div>
	<div class="crt-corner crt-corner-tr"></div>
	<div class="crt-corner crt-corner-bl"></div>
	<div class="crt-corner crt-corner-br"></div>
	<div class="crt-rim crt-rim-top"></div>
	<div class="crt-rim crt-rim-bottom"></div>
{/if}
