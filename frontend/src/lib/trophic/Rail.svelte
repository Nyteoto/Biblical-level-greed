<script lang="ts">
	/**
	 * The whole of the app's navigation, and the reason the screens stopped
	 * repeating themselves.
	 *
	 * ## It selects a lens, not a place
	 *
	 * The tab bar this replaces treated each tab as a *destination*, so every
	 * screen had to carry everything about that destination — and the same fact
	 * ended up stated three or four times in different wrappers, because every
	 * screen wanted to be self-sufficient.
	 *
	 * These five are not destinations. Four of them are **questions asked of one
	 * subject**, and the subject is the folder and year in the URL:
	 *
	 *   - **Map** — what did the year look like?
	 *   - **Log** — what happened on this day?
	 *   - **Threads** — what is still open?
	 *   - **Record** — what is this folder, in figures?
	 *
	 * The scope survives every switch (see `scope.ts`), which is what makes them
	 * lenses rather than screens. It is also why the heatmap belongs on Map and
	 * nowhere else: the Log has no business redrawing the year, because the year
	 * is a different question and there is a key for it.
	 *
	 * Capture is the fifth and is deliberately not one of the four — it has no
	 * subject, because you have not written the line yet.
	 *
	 * ## The gauge
	 *
	 * The open-todo count against its cap, as ten ticks. A number that can only
	 * go to ten is better drawn than written, and it belongs in the rail because
	 * it is true of the whole app rather than of any lens. It is a count and not
	 * a verdict: no streak, no target, nothing that reads as being behind.
	 */
	import { page } from '$app/state';
	import { banner } from '$lib/trophic/banner-state.svelte';
	import { readScope, lensHref } from './scope';

	const strip = banner();
	const scope = $derived(readScope(page.url));
	const at = $derived(page.url.pathname);

	/** The cap comes back with the count, so the gauge is never drawing against
	 *  a length this file invented — `MAX_OPEN_TODOS` is the server's and it is
	 *  on every `/banner` read. Ten until the first one lands. */
	const slots = $derived(strip.data?.cap ?? 10);
	const taken = $derived(Math.min(slots, strip.data?.open ?? 0));

	const LENSES = [
		{ href: '/', label: 'Capture', match: (p: string) => p === '/' },
		{ href: '/map', label: 'Map', match: (p: string) => p.startsWith('/map') },
		{ href: '/log', label: 'Log', match: (p: string) => p.startsWith('/log') },
		{ href: '/threads', label: 'Threads', match: (p: string) => p.startsWith('/threads') },
		{ href: '/record', label: 'Record', match: (p: string) => p.startsWith('/record') }
	];
</script>

<nav
	aria-label="Lenses"
	class="flex w-[64px] shrink-0 flex-col items-center gap-1 py-[14px] pb-4"
	style="box-shadow:inset -1px 0 0 0 var(--color-neutral-400)"
>
	{#each LENSES as lens (lens.href)}
		{@const on = lens.match(at)}
		<!-- Capture keeps no scope: it is the one key that is not a question
		     about a folder. -->
		<a
			href={lens.href === '/' ? '/' : lensHref(lens.href, scope)}
			aria-label={lens.label}
			aria-current={on ? 'page' : undefined}
			title={lens.label}
			class="flex h-12 w-12 items-center justify-center transition-colors {on
				? 'accent-fill'
				: 'text-neutral-600 hover:text-ink'}"
		>
			{#if lens.label === 'Capture'}
				<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m5 7 5 5-5 5" /><path d="M13 17h6" /></svg>
			{:else if lens.label === 'Map'}
				<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M4 4h16v16H4z" /><path d="M4 9.33h16M4 14.67h16M9.33 4v16M14.67 4v16" /></svg>
			{:else if lens.label === 'Log'}
				<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h9" /></svg>
			{:else if lens.label === 'Threads'}
				<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><circle cx="6.5" cy="6" r="2.2" /><circle cx="17.5" cy="18" r="2.2" /><path d="M6.5 8.2v5.3a2 2 0 0 0 2 2h6.8" /></svg>
			{:else}
				<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><path d="M6 19v-6M12 19V5M18 19v-9" /></svg>
			{/if}
		</a>
	{/each}

	<span class="flex-grow"></span>

	<!-- Filled from the bottom, because that is the direction it fills in. -->
	<span
		class="mb-[14px] flex flex-col-reverse gap-[3px]"
		aria-label="{taken} of {slots} todo slots taken"
		title="{taken} of {slots} todo slots taken"
	>
		{#each Array(slots) as _, i (i)}
			<span
				class="h-[6px] w-[18px]"
				style={i < taken
					? 'background:var(--color-accent)'
					: 'box-shadow:inset 0 0 0 1px var(--color-neutral-500)'}
			></span>
		{/each}
	</span>

	<a
		href="/settings"
		aria-label="Settings"
		title="Settings"
		aria-current={at.startsWith('/settings') || at.startsWith('/manual') ? 'page' : undefined}
		class="flex h-12 w-12 items-center justify-center transition-colors {at.startsWith(
			'/settings'
		) || at.startsWith('/manual')
			? 'text-ink'
			: 'text-neutral-600 hover:text-ink'}"
	>
		<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true"><path d="M4 8h8M16.5 8H20M4 16h4M12.5 16H20" /><circle cx="14.2" cy="8" r="2.2" /><circle cx="10.2" cy="16" r="2.2" /></svg>
	</a>
</nav>
