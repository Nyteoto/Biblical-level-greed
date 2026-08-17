<script lang="ts">
	import '../app.css';
	// Trophic's animation vocabulary, and the `.trophic` scope below that its
	// reduced-motion rule keys off. It sits at the root now rather than on the
	// capture route group: Settings and the Manual are Trophic's screens too,
	// and they were the two that quietly opted out of it.
	import '$lib/trophic/trophic.css';
	import UploadBar from '$lib/trophic/UploadBar.svelte';
	import { browser } from '$app/environment';
	import { barrelMap, barrelScale, CORNER_PX } from '$lib/trophic/crt';

	let { children } = $props();

	// The curve's displacement map. Built once, in the browser only — it is a
	// canvas — and injected into the filter below. Until it lands the filter has
	// no map and `feDisplacementMap` is a no-op, so the app renders flat rather
	// than broken during SSR and first paint.
	const map = $derived(browser ? barrelMap() : '');

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
<!-- The curve's filter. `preserveAspectRatio="none"` stretches the square map
     over whatever shape the viewport is; the map is a normalised field, so the
     magnitude comes from `scale` rather than from the pixels. See `crt.ts`. -->
<svg width="0" height="0" aria-hidden="true" focusable="false" class="absolute">
	<defs>
		<filter
			id="crt-barrel"
			x="-4%"
			y="-4%"
			width="108%"
			height="108%"
			color-interpolation-filters="sRGB"
		>
			<feImage href={map} preserveAspectRatio="none" result="map" />
			<feDisplacementMap
				in="SourceGraphic"
				in2="map"
				scale={map ? barrelScale(CORNER_PX) : 0}
				xChannelSelector="R"
				yChannelSelector="G"
			/>
		</filter>
	</defs>
</svg>

<div data-shell-header class="trophic flex min-h-dvh flex-col">
	<!-- Above the page: an upload outlives the screen that started it, so its
	     progress belongs to the shell rather than to the capture bar.
	     It is `sticky`, and it stays *outside* the curve for that reason — a
	     filtered ancestor becomes the containing block for anything positioned
	     inside it, which would anchor this to the page instead of the viewport. -->
	<UploadBar />

	<!-- Only the page content is curved. Everything the glass does is done by
	     the layers below instead, which are flat, fixed and know nothing about
	     what they are over. -->
	<main class="crt-screen flex flex-1 flex-col">
		{@render children()}
	</main>
</div>

<!-- The glass. Five layers, over everything, `pointer-events: none`, entirely
     unaware of the app underneath — which is what lets the app be rewritten
     without any of this having to move. -->
<div class="crt crt-glow"></div>
<div class="crt crt-grain"></div>
<div class="crt crt-scan"></div>
<div class="crt crt-vignette"></div>
