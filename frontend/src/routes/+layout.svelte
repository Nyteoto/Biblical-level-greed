<script lang="ts">
	import { page } from '$app/state';
	import '../app.css';
	import { EXPECTED_API, getApiVersion, restartServer } from '$lib/api';
	import { sitting } from '$lib/portal/sitting.svelte';

	let { children } = $props();

	/**
	 * Press feedback, for everything, from one place.
	 *
	 * `pointerdown` and not `click`: the point is to answer the finger, and a
	 * click arrives on release. Capture phase, so a component calling
	 * `stopPropagation` on its own handler cannot silently opt out of being
	 * responsive.
	 */
	const PRESSABLE = 'button, a[href], [role="button"], [role="radio"], summary';

	$effect(() => {
		function press(event: PointerEvent) {
			const from = event.target as Element | null;
			// A label only when it wraps its own input — which is how every file
			// picker in the Portal is built.
			const el = (from?.closest?.(PRESSABLE) ??
				from?.closest?.('label:has(input)')) as HTMLElement | null;
			if (!el || (el as HTMLButtonElement).disabled) return;

			// Restart rather than ignore a second press inside the first flash.
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
	 * A backend change ships, the long-running service keeps serving the old
	 * Python, and the page looks broken for reasons that are nowhere in the
	 * source. Asked once on start, because a restart is the only thing that
	 * can change the answer and a restart reloads this page anyway.
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
		setTimeout(() => location.reload(), 4000);
	}

	const onSettings = $derived(page.url.pathname.startsWith('/settings'));
</script>

<svelte:head>
	<title>Portal</title>
</svelte:head>

<!--
	**The shell owns the viewport, and the screen scrolls inside itself.**
	`h-dvh overflow-hidden` here and `min-h-0 flex-1` on the screen: a page
	that has not said how it scrolls is clipped rather than quietly pushing the
	document past the window.
-->
<div data-shell-header class="portal flex h-dvh flex-col overflow-hidden">
	{#if stale}
		<div class="flex shrink-0 flex-wrap items-center gap-3 bg-accent-100 px-6 py-2.5 text-[12px]">
			<span class="font-semibold text-accent-700">
				The server is running older code than this page.
			</span>
			<button
				type="button"
				class="accent-fill ml-auto px-3 py-1.5 text-[12px] font-semibold disabled:opacity-50"
				disabled={restarting}
				onclick={restart}
			>
				{restarting ? 'Restarting…' : 'Restart server'}
			</button>
		</div>
	{/if}

	<main class="relative flex min-h-0 flex-1 flex-col overflow-hidden">
		{@render children()}
	</main>

	<!-- The one way off the Portal, and it is withheld during a sitting: leaving
	     the page is what ends the day, and a link that did it would be a trap. -->
	{#if !sitting.token}
		<a
			href={onSettings ? '/' : '/settings'}
			class="fixed right-4 bottom-[calc(env(safe-area-inset-bottom)+12px)] z-20 px-2 py-1 text-[11px] tracking-[0.12em] text-neutral-600 uppercase transition-colors hover:text-ink"
		>
			{onSettings ? 'Portal' : 'Settings'}
		</a>
	{/if}
</div>
