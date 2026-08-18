<script lang="ts">
	/**
	 * Everything you can change about a folder, opened where you held it.
	 *
	 * This used to be a dropdown behind a small button in the album header, and
	 * it was the only route to any of it: rename, lifecycle, which tags point
	 * here, delete. A screen you have to be *on* in order to rename the thing
	 * you are looking at is a screen doing navigation's job, so the button is
	 * gone and this opens from the folder wherever the folder is drawn — the
	 * year shelf's cards and the album sidebar's rows both.
	 *
	 * That is the whole argument for the hold gesture: the panel goes to the
	 * object rather than the object being carried to the panel. One component
	 * for both surfaces so the two can never drift into offering different
	 * powers over the same folder.
	 *
	 * Mapping a loose tag is in here for the same reason. It is the one edit
	 * that otherwise costs a trip to `/mapping`, and it is retroactive — point
	 * `<deploy>` here and every line ever written with it joins, with nothing
	 * migrated. Membership is resolved, never stored; this panel only ever moves
	 * the pointer.
	 *
	 * It clamps into the viewport after mounting, because it opens under a
	 * finger and a finger is often near an edge — the same reason
	 * `FolderAssignMenu` does.
	 */
	import { phosphorize } from './colors';
	import Segmented from './Segmented.svelte';
	import type { Folder, UnassignedTag } from './api';

	let {
		x,
		y,
		folder,
		unassigned = [],
		onpatch,
		ondelete,
		onclose
	}: {
		x: number;
		y: number;
		folder: Folder;
		unassigned?: UnassignedTag[];
		onpatch: (change: {
			name?: string;
			state?: string;
			add_tags?: string[];
			remove_tags?: string[];
		}) => void;
		ondelete: () => void;
		onclose: () => void;
	} = $props();

	let panel = $state<HTMLDivElement | null>(null);
	// Capturing the initial position is the intent: it opens where the hold
	// was, and a new hold is a new instance of this component.
	// svelte-ignore state_referenced_locally
	let pos = $state({ x, y });

	let renaming = $state(false);
	let renameValue = $state('');

	$effect(() => {
		const el = panel;
		if (!el) return;
		const box = el.getBoundingClientRect();
		const margin = 12;
		const nx = Math.min(pos.x, window.innerWidth - box.width - margin);
		const ny = Math.min(pos.y, window.innerHeight - box.height - margin);
		pos = { x: Math.max(margin, nx), y: Math.max(margin, ny) };
	});

	const STATES = [
		{ value: '', label: 'open' },
		{ value: 'active', label: 'running' },
		{ value: 'shipped', label: 'shipped' }
	];

	function submitRename() {
		const next = renameValue.trim();
		renaming = false;
		if (!next || next === folder.name) return;
		onpatch({ name: next });
	}
</script>

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="fixed inset-0 z-[9700]"
	onclick={onclose}
	oncontextmenu={(e) => {
		e.preventDefault();
		onclose();
	}}
>
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		bind:this={panel}
		class="absolute flex w-[290px] flex-col gap-3 rounded-[14px] bg-surface p-4 shadow-lg"
		style="left:{pos.x}px; top:{pos.y}px; animation:landing-fade-in 0.15s ease-out"
		onclick={(e) => e.stopPropagation()}
	>
		{#if renaming}
			<form
				onsubmit={(e) => {
					e.preventDefault();
					submitRename();
				}}
			>
				<!-- svelte-ignore a11y_autofocus -->
				<input
					autofocus
					bind:value={renameValue}
					aria-label="folder name"
					class="w-full rounded-lg bg-neutral-200 px-3 py-2 text-[14px]"
					onkeydown={(e) => {
						if (e.key === 'Escape') renaming = false;
					}}
				/>
			</form>
		{:else}
			<button
				type="button"
				class="flex items-baseline gap-2 text-left text-[14px] font-semibold"
				onclick={() => {
					renameValue = folder.name;
					renaming = true;
				}}
			>
				<span
					class="h-2 w-2 shrink-0 self-center rounded-full"
					style="background:{phosphorize(folder.color)}"
				></span>
				{folder.name}
				<span class="text-[12px] font-normal text-neutral-700">rename</span>
			</button>
		{/if}

		<!-- Three states and no taxonomy: the empty one is the default, and a
		     folder never marked is an interest rather than a project. -->
		<Segmented
			options={STATES}
			value={folder.state ?? ''}
			onpick={(state) => onpatch({ state })}
			label="this folder's state"
		/>

		<!-- What points here. The mapping *is* the folder, so it is shown as the
		     definition rather than as a summary, and each tag is a button that
		     removes itself. -->
		<div class="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-[12px]">
			{#each folder.tags as tag (tag)}
				<button
					type="button"
					class="font-mono transition-colors hover:text-accent-700"
					style="color:var(--color-accent-700)"
					title="click to unmap"
					onclick={() => onpatch({ remove_tags: [tag] })}
				>
					{`<${tag}>`}
				</button>
			{:else}
				<span class="text-neutral-700">no tags point here yet</span>
			{/each}
		</div>

		{#if unassigned.length > 0}
			<!-- The loose tags, right here. This is the trip to the mapping screen
			     that the hold gesture exists to remove. -->
			<div class="flex flex-wrap gap-2 rounded-[10px] bg-neutral-200 p-2.5 text-[12px]">
				{#each unassigned.slice(0, 10) as tag (tag.tag)}
					<button
						type="button"
						class="font-mono transition-colors hover:opacity-70"
						style="color:var(--color-neutral-800)"
						title="point this tag here"
						onclick={() => onpatch({ add_tags: [tag.tag] })}
					>
						{`<${tag.tag}>`}<span class="ml-1 text-neutral-700">×{tag.count}</span>
					</button>
				{/each}
			</div>
		{/if}

		<button
			type="button"
			class="self-start text-[12px] font-semibold text-accent-700"
			onclick={ondelete}
		>
			Delete this folder
		</button>
	</div>
</div>
