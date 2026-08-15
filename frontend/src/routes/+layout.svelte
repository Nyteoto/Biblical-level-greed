<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import XpMeter from '$lib/components/XpMeter.svelte';
	import UploadBar from '$lib/trophic/UploadBar.svelte';
	import { xpState } from '$lib/xpstore.svelte';

	let { children } = $props();

	// Capture is the app now, so it holds the root and leads the bar. The tech
	// tree is support: it still has its own screens, its own log and its own
	// index, and the two share a data root and a process rather than a model.
	// The Manual lives under Settings — read closely once and skimmed rarely
	// after that, which does not earn a permanent tab.
	const tabs = [
		{ href: '/', label: 'Capture' },
		{ href: '/log', label: 'Log' },
		{ href: '/today', label: 'Today' },
		{ href: '/tree', label: 'Trees' },
		{ href: '/settings', label: 'Settings' }
	];

	// `/log` and `/folders/x` are both the log's territory, so the Log tab
	// stays lit while reading a folder.
	const isActive = (href: string) =>
		href === '/'
			? page.url.pathname === '/'
			: href === '/log'
				? ['/log', '/folders', '/mapping'].some((p) => page.url.pathname.startsWith(p))
				: page.url.pathname.startsWith(href);
</script>

<svelte:head>
	<title>Personal Growth System</title>
</svelte:head>

<div class="flex min-h-dvh flex-col bg-[#14100c] text-stone-300">
	<!-- Centred uppercase tabs, as in the reference. -->
	<header class="relative border-b border-black/60 bg-gradient-to-b from-[#20191200] to-[#00000060]">
		<div class="flex h-11 items-stretch justify-center gap-1">
			{#each tabs as tab}
				<a
					href={tab.href}
					class="relative flex items-center px-5 text-[12px] font-semibold tracking-[0.22em] uppercase transition
					{isActive(tab.href)
						? 'text-amber-300'
						: 'text-stone-500 hover:text-stone-300'}"
				>
					{tab.label}
					{#if isActive(tab.href)}
						<span class="absolute inset-x-3 bottom-0 h-[2px] bg-amber-400/80"></span>
					{/if}
				</a>
			{/each}
		</div>

		<!-- XP rides in the corner, on every page. It decides what you can start
		     now, so it cannot live on one screen you have to go and look at. -->
		{#if xpState.xp}
			<div class="absolute inset-y-0 right-3 flex items-center">
				<XpMeter xp={xpState.xp} />
			</div>
		{/if}
	</header>

	<!-- Above the page, below the tabs: an upload outlives the screen that
	     started it, so its progress belongs to the shell. -->
	<UploadBar />

	<main class="flex-1">
		{@render children()}
	</main>
</div>
