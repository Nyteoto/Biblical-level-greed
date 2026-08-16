<script lang="ts">
	/**
	 * The floating menu for filing an entry into a folder by hand.
	 * Ported from `components/FolderAssignMenu.tsx`.
	 *
	 * Three behaviours in it are not decoration:
	 *   - it clamps itself into the viewport after mounting, because it opens
	 *     at the pointer and the pointer is often near an edge;
	 *   - the search box is focused on a mouse but never on a touch screen,
	 *     where focusing it would throw the keyboard over the list it filters;
	 *   - the radio dot is the current filing, so the menu says where the
	 *     entry already is rather than only offering somewhere to put it.
	 */
	import type { Folder } from './api';

	let {
		x,
		y,
		folders,
		current = null,
		onselect,
		onclear,
		onclose
	}: {
		x: number;
		y: number;
		folders: Folder[];
		current?: string | null;
		onselect: (folderId: string) => void;
		onclear: () => void;
		onclose: () => void;
	} = $props();

	let menu = $state<HTMLDivElement | null>(null);
	let search = $state<HTMLInputElement | null>(null);
	// Capturing the initial position is the intent: the menu opens where the
	// pointer was, and a new open is a new instance of this component.
	// svelte-ignore state_referenced_locally
	let pos = $state({ x, y });
	let query = $state('');

	$effect(() => {
		const el = menu;
		if (!el) return;

		const box = el.getBoundingClientRect();
		const margin = 8;
		let nx = x;
		let ny = y;
		if (x + box.width + margin > window.innerWidth) nx = window.innerWidth - box.width - margin;
		if (y + box.height + margin > window.innerHeight) ny = window.innerHeight - box.height - margin;
		pos = { x: Math.max(nx, margin), y: Math.max(ny, margin) };

		if (!window.matchMedia('(pointer: coarse) and (hover: none)').matches) {
			const t = setTimeout(() => search?.focus(), 10);
			return () => clearTimeout(t);
		}
	});

	function outside(event: Event) {
		if (menu && !menu.contains(event.target as Node)) onclose();
	}

	const filtered = $derived(
		query.trim()
			? folders.filter((f) => f.name.toLowerCase().includes(query.trim().toLowerCase()))
			: folders
	);
</script>

<svelte:document onmousedown={outside} ontouchstart={outside} />
<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<div
	bind:this={menu}
	class="fixed z-[120] flex max-w-[260px] min-w-[200px] flex-col rounded-[14px] bg-surface py-2 shadow-lg"
	style="left:{pos.x}px;top:{pos.y}px;animation:landing-fade-in 0.12s ease-out"
>
	<div class="px-2.5 pb-2">
		<div class="px-1 pt-0.5 pb-2 text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">
			assign to folder
		</div>
		<input
			bind:this={search}
			bind:value={query}
			placeholder="search…"
			class="w-full rounded-lg bg-neutral-200 px-2.5 py-1.5 text-[12px]"
		/>
	</div>

	<div class="trophic-scrollbar-hide max-h-[220px] overflow-y-auto py-1">
		{#if folders.length === 0}
			<div class="px-3 py-2 text-[12px] text-neutral-700">no folders yet.</div>
		{:else if filtered.length === 0}
			<div class="px-3 py-2 text-[12px] text-neutral-700">no match.</div>
		{:else}
			{#each filtered as f (f.id)}
				{@const active = f.id === current}
				<button
					type="button"
					class="mx-1.5 flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition-colors {active
						? 'bg-neutral-200 font-semibold'
						: 'hover:bg-neutral-200'}"
					onclick={() => {
						onselect(f.id);
						onclose();
					}}
				>
					<span class="shrink-0" style="color:{f.color}">{active ? '●' : '○'}</span>
					<span class="truncate">{f.name}</span>
				</button>
			{/each}
		{/if}
	</div>

	{#if current}
		<div class="mt-1 px-1.5">
			<button
				type="button"
				class="w-full rounded-lg px-2.5 py-1.5 text-left text-[12px] text-neutral-700 transition-colors hover:bg-neutral-200 hover:text-accent-700"
				onclick={() => {
					onclear();
					onclose();
				}}
			>
				remove manual assignment
			</button>
		</div>
	{/if}
</div>
