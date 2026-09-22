<script lang="ts">
	import { page } from '$app/state';
	import '../app.css';
	// Trophic's animation vocabulary, and the `.trophic` scope below that its
	// reduced-motion rule keys off. It sits at the root now rather than on the
	// capture route group: Settings and the Manual are Trophic's screens too,
	// and they were the two that quietly opted out of it.
	import '$lib/trophic/trophic.css';
	import UploadBar from '$lib/trophic/UploadBar.svelte';
	import HoldRing from '$lib/trophic/HoldRing.svelte';
	import Banner from '$lib/trophic/Banner.svelte';
	import Rail from '$lib/trophic/Rail.svelte';
	import SubjectBar from '$lib/trophic/SubjectBar.svelte';
	import { banner } from '$lib/trophic/banner-state.svelte';
	import { EXPECTED_API, getApiVersion, restartServer } from '$lib/api';

	let { children } = $props();

	// The tech tree's own screens. They share this shell and nothing else — see
	// the rail below.
	const tree = $derived(
		page.url.pathname.startsWith('/today') || page.url.pathname.startsWith('/tree')
	);

	/**
	 * The four lenses, which are the four screens that *have* a subject.
	 *
	 * Capture has none — you have not written the line yet, which is the same
	 * reason the rail's Capture key carries no scope. Settings and the Manual
	 * are about the app rather than about a folder. So the bar is drawn on
	 * exactly the screens that are questions about something.
	 */
	const lens = $derived(
		['/map', '/log', '/threads', '/record'].some((p) => page.url.pathname.startsWith(p))
	);

	// The standing strip's one owner. Started here because it is drawn here, and
	// its slow tick is cleared on teardown so a hot reload leaves nothing behind.
	$effect(() => banner().start());


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

	/**
	 * Is the server older than the page in front of it?
	 *
	 * This has bitten three times and it is invisible every time: a backend
	 * change ships, the long-running service keeps serving the old Python, and
	 * the app looks broken for reasons that are nowhere in the source — a save
	 * that does nothing, a setting that never applies, a field that is always
	 * empty. Asked once on start, because a restart is the only thing that can
	 * change the answer and a restart reloads this page anyway.
	 *
	 * Only when the server is *older*. A newer server against a stale page is
	 * the other half of the same problem and its fix is a reload, not a restart
	 * — telling somebody to restart a service that is already current sends them
	 * chasing something that is not wrong.
	 */
	let stale = $state(false);
	let restarting = $state(false);

	$effect(() => {
		getApiVersion()
			.then((v) => (stale = v.api < EXPECTED_API))
			.catch(() => {
				/* the server being unreachable is its own, visible, problem */
			});
	});

	async function restart() {
		restarting = true;
		try {
			await restartServer();
		} catch {
			/* it may well die mid-reply — that is the request working */
		}
		// Give systemd its moment, then come back on the new process.
		setTimeout(() => location.reload(), 4000);
	}

	// The shell is a ground, the rail, an upload bar and the page.
	//
	// **Navigation lives here now.** It used to be one pill that each screen
	// placed for itself, because the three tabs did not sit in the same corner
	// on all of them. The rail is not a tab bar: it selects a *lens* on one
	// subject — the folder and year in the URL — and that subject survives every
	// switch, which is the whole architecture. A thing that is the same on every
	// screen belongs to the shell.
</script>

<svelte:head>
	<title>Trophic</title>
</svelte:head>

<!-- `data-shell-header` is what claims the status-bar inset on an installed
     phone. It is an attribute rather than a `header` selector because the Log's
     day headings are `header` elements too, and every one of them was quietly
     padding itself by the height of the notch. -->

<!-- The hold gesture, over everything and belonging to nothing. Mounted at the
     root because it is the app's, not a screen's. -->
<HoldRing />

<!--
	**The shell owns the viewport, and each lens scrolls inside itself.**

	It was `min-h-dvh`, which let it grow — and every screen that then set its
	own `h-dvh` was a full viewport *below* the banner, so the document was
	always taller than the window by the height of the strip. The rail and the
	banner scrolled away with the page, the Log pinned its furniture and Record
	did not, and nothing agreed about what a screenful was.

	Pinned, the arithmetic is done once: the rail and the strip take what they
	need and the page gets the remainder, which is what `min-h-0 flex-1` on the
	four lenses has been asking for all along.

	**The tech tree is the exception and stays a document.** `/today` and
	`/tree` are the sibling app sharing this shell; they are long pages meant to
	be scrolled, not instruments with furniture to hold still, and they do not
	carry the rail either.
-->
<div
	data-shell-header
	class="trophic flex {tree ? 'min-h-dvh' : 'h-dvh overflow-hidden'}"
>
	<!-- The rail is capture's. The tech tree at `/today` and `/tree` is a
	     sibling app sharing this shell — it never carried the tab bar either,
	     and every key in the rail would take you out of it. -->
	{#if !tree}
		<Rail />
	{/if}

	<div class="flex min-w-0 flex-1 flex-col">
	<!-- Above everything the app draws, because nothing below it can be trusted
	     to mean what it says while this is true. -->
	{#if stale}
		<div
			class="flex shrink-0 flex-wrap items-center gap-3 bg-accent-100 px-[34px] py-2.5 text-[12px]"
		>
			<span class="font-semibold text-accent-700">
				The server is running older code than this app.
			</span>
			<span class="text-neutral-700">
				Saving and settings may do nothing until it restarts.
			</span>
			<button
				type="button"
				class="accent-fill ml-auto rounded-[9px] px-3 py-1.5 text-[12px] font-semibold disabled:opacity-50"
				disabled={restarting}
				onclick={restart}
			>
				{restarting ? 'Restarting…' : 'Restart server'}
			</button>
		</div>
	{/if}

	<!-- Above the page: an upload outlives the screen that started it, so its
	     progress belongs to the shell rather than to the capture bar. It is
	     fixed, and it stays outside `main` so that nothing a page does to its
	     own subtree — a transform, most of all — can become its containing
	     block and anchor it to the page instead of the viewport. -->
	<UploadBar />

	<!-- The standing strip, above the content on every screen. It sits inside
	     the shell rather than inside `main` so it is not re-created by every
	     page that renders. -->
	<Banner />

		<!-- **The rail is the question; this is the subject.** Both belong to the
		     shell and neither to a lens — which is the half of the navigation
		     that was missing, and the reason a folder could only be chosen from
		     inside Map. See `SubjectBar`. -->
		{#if lens}
			<SubjectBar />
		{/if}

		<!-- `overflow-hidden`, so a page that has not said how it scrolls is
		     clipped rather than quietly pushing the shell past the window. That
		     is the failure being fixed here, and it is the kind that is invisible
		     until the rail slides off the top. -->
		<main class="flex min-h-0 flex-1 flex-col {tree ? '' : 'overflow-hidden'}">
			{@render children()}
		</main>
	</div>
</div>

