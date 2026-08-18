<script lang="ts">
	/**
	 * The whole of the app's navigation: three words in one small white pill.
	 *
	 * **It goes in the same corner on every screen** — the page's own top left,
	 * at `px-[34px] pt-[22px]` — and it is the same size everywhere. It briefly
	 * did not: the Log put it at the top of its content column and the album put
	 * a smaller copy at the top of the sidebar, so the one control that is on
	 * all four screens was the one that moved between them. A navigation control
	 * you have to look for is worse than one that takes a little more room.
	 *
	 * It stays a component each screen places, rather than something the shell
	 * draws over the top, because these are full-height layouts with their own
	 * scroll regions and a floating pill would have to be padded around by every
	 * one of them anyway.
	 */
	import { page } from '$app/state';
	import { lastAlbum } from './lastalbum.svelte';

	$effect(() => {
		lastAlbum.hydrate();
	});

	const path = $derived(page.url.pathname);
	const onShelf = $derived(path.startsWith('/log'));
	const inAlbum = $derived(path.startsWith('/folders'));

	/**
	 * Log is a toggle once you are inside it, because the Log is two screens and
	 * had no route between them. The year shelf is the index and an album is the
	 * reading; `Opens on: latest day` skips the index, the album sidebar prints
	 * the year as a heading rather than a link, and the redirect replaces its
	 * history entry — so the shelf was somewhere you could arrive and never
	 * return to. From an album this goes back to the shelf, and `?shelf` is what
	 * stops `+page.ts` bouncing you straight out again.
	 *
	 * From the shelf it goes back to whatever you were last reading, and when
	 * there is nothing to go back to it stays an ordinary link to the shelf.
	 */
	const logHref = $derived(
		inAlbum ? '/log?shelf' : onShelf ? (lastAlbum.href ?? '/log') : '/log'
	);

	const logTitle = $derived(
		inAlbum ? 'back to the year shelf' : onShelf && lastAlbum.href ? 'back to what you were reading' : undefined
	);

	const tabs = $derived([
		{ href: '/', label: 'Capture', title: undefined as string | undefined },
		{ href: logHref, label: 'Log', title: logTitle },
		{ href: '/settings', label: 'Settings', title: undefined as string | undefined }
	]);

	// `/log`, an album and the mapping screen are all the Log's territory, and
	// the Manual is Settings'. A tab that goes dark when you follow a link out
	// of it makes the app feel like it has more places in it than it has.
	const isActive = (label: string) =>
		label === 'Capture'
			? path === '/'
			: label === 'Log'
				? onShelf || inAlbum
				: ['/settings', '/mapping', '/manual'].some((p) => path.startsWith(p));
</script>

<nav
	class="flex w-fit items-center gap-1 self-start rounded-[11px] bg-surface p-1 shadow-sm"
	aria-label="sections"
>
	{#each tabs as tab (tab.label)}
		{@const on = isActive(tab.label)}
		<a
			href={tab.href}
			title={tab.title}
			aria-current={on ? 'page' : undefined}
			class="rounded-lg px-[14px] py-[7px] text-[12px] tracking-[0.06em] transition-colors {on
				? 'accent-fill font-bold'
				: 'font-semibold text-neutral-700 hover:text-ink'}"
		>
			{tab.label}
		</a>
	{/each}
</nav>
