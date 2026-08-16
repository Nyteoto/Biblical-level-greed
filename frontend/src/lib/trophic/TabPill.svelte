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

	const tabs = [
		{ href: '/', label: 'Capture' },
		{ href: '/log', label: 'Log' },
		{ href: '/settings', label: 'Settings' }
	];

	// `/log`, an album and the mapping screen are all the Log's territory, and
	// the Manual is Settings'. A tab that goes dark when you follow a link out
	// of it makes the app feel like it has more places in it than it has.
	const isActive = (href: string) =>
		href === '/'
			? page.url.pathname === '/'
			: href === '/log'
				? ['/log', '/folders'].some((p) => page.url.pathname.startsWith(p))
				: ['/settings', '/mapping', '/manual'].some((p) => page.url.pathname.startsWith(p));
</script>

<nav
	class="flex w-fit items-center gap-1 self-start rounded-[11px] bg-surface p-1 shadow-sm"
	aria-label="sections"
>
	{#each tabs as tab (tab.href)}
		{@const on = isActive(tab.href)}
		<a
			href={tab.href}
			aria-current={on ? 'page' : undefined}
			class="rounded-lg px-[14px] py-[7px] text-[12px] tracking-[0.06em] transition-colors {on
				? 'accent-fill font-bold'
				: 'font-semibold text-neutral-700 hover:text-ink'}"
		>
			{tab.label}
		</a>
	{/each}
</nav>
