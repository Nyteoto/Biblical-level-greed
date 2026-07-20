<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';

	let { children } = $props();

	const tabs = [
		{ href: '/', label: 'Today' },
		{ href: '/tree', label: 'Tech Tree' },
		{ href: '/manual', label: 'Manual' }
	];

	const isActive = (href: string) =>
		href === '/' ? page.url.pathname === '/' : page.url.pathname.startsWith(href);
</script>

<div class="flex min-h-screen flex-col bg-[#14100c] text-stone-300">
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
	</header>

	<main class="flex-1">
		{@render children()}
	</main>
</div>
