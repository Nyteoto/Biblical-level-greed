<script lang="ts">
	/**
	 * The whole of the app's navigation: three words in one small white pill.
	 *
	 * It is a component rather than a strip in the layout because it does not
	 * sit in the same place on every screen. Capture and Settings put it top
	 * left of the page; the Log puts it at the top of the left column, above the
	 * year rail's content or the album list, because that column is where the
	 * eye already is. A shell that owned it would have to know which, and the
	 * Log would end up with two headers.
	 */
	import { page } from '$app/state';

	let { compact = false }: { compact?: boolean } = $props();

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
	class="flex items-center gap-1 self-start rounded-[11px] bg-surface p-1 shadow-sm"
	aria-label="sections"
>
	{#each tabs as tab (tab.href)}
		{@const on = isActive(tab.href)}
		<a
			href={tab.href}
			aria-current={on ? 'page' : undefined}
			class="rounded-lg py-[7px] text-[12px] tracking-[0.06em] transition-colors {compact
				? 'px-[11px]'
				: 'px-[14px]'} {on
				? 'accent-fill font-bold'
				: 'font-semibold text-neutral-700 hover:text-ink'}"
		>
			{tab.label}
		</a>
	{/each}
</nav>
