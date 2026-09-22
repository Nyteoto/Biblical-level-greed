<script lang="ts">
	/**
	 * Choosing the subject — every folder there is, under the bar that names it.
	 *
	 * ## Why this is in the shell and not on a lens
	 *
	 * It was Record's left column, and before that Map's chip row, and before
	 * that the year shelf's cards. Three drawings of one list, each owned by
	 * whichever lens happened to need it first — and none of them reachable from
	 * the other three. Choosing a folder is not a thing you do *on Map*. It is a
	 * thing you do, and then ask a question about.
	 *
	 * So the list moved to where the rail already is: the shell. A row press
	 * sets `?folder=` and **leaves you on the lens you were on**, which is the
	 * first time the scope has been changeable without travelling.
	 *
	 * ## It keeps every power the column had
	 *
	 * A hold on a row opens `FolderPanel` — rename, state, group, tags, delete.
	 * A hold on a heading opens `GroupPanel`, and a drag rearranges the shelf
	 * through `sortable`. `+ new folder` is here because this is the only list
	 * left, so it is the only place a folder can be made.
	 *
	 * The reading is `splitShelf` from `shelf.ts`, the same function the shelf
	 * has always been read with — so what is loose and what is under a heading
	 * cannot disagree with anything else that asks.
	 */
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import {
		createFolder,
		deleteFolder,
		deleteGroup,
		orderGroups,
		patchFolder,
		renameGroup,
		setFolderGroup,
		type Album,
		type Folder
	} from './api';
	import { lensHref, readScope } from './scope';
	import { reorderGroups, splitShelf } from './shelf';
	import { subject } from './subject.svelte';
	import { collapsedGroups } from './collapsed.svelte';
	import { hold } from './hold';
	import { sortable } from './sortable';
	import { toRamp } from './colors';
	import FolderPanel from './FolderPanel.svelte';
	import GroupPanel from './GroupPanel.svelte';

	let {
		x,
		y,
		onclose
	}: {
		/** Where the bar's folder button is, so the list hangs under the name it
		 *  is a list of. Measured by the bar and passed down: this panel is
		 *  `fixed` — it has to escape the shell's clip — and a `fixed` box
		 *  cannot find its opener by itself. */
		x: number;
		y: number;
		onclose: () => void;
	} = $props();

	const bar = subject();
	const scope = $derived(readScope(page.url));
	const shelf = $derived(bar.data);

	let error = $state<string | null>(null);
	let creating = $state(false);
	let newName = $state('');
	let panel = $state<{ folder: Folder; x: number; y: number } | null>(null);
	let groupPanel = $state<{ name: string; x: number; y: number } | null>(null);
	/** The loose tags, for the held panel's one retroactive edit. The subject
	 *  bar's, read once for the whole app: this and Record both fetched their
	 *  own and neither refetched, so a tag claimed on one was still on offer
	 *  in the other. */
	const unassigned = $derived(bar.tags);

	const folded = collapsedGroups();
	const loose = $derived(splitShelf(shelf).loose);
	const sections = $derived(splitShelf(shelf).sections);

	/** **The whole point: the lens does not change.** `page.url.pathname` is
	 *  where you are, and the scope is what you are asking about — so picking a
	 *  folder rewrites the second and leaves the first alone. */
	function choose(folder: string | null) {
		onclose();
		goto(lensHref(page.url.pathname, { ...scope, folder }), {
			noScroll: true,
			keepFocus: true
		});
	}

	/** Every edit re-reads the shelf once, in the store, so the lens under this
	 *  panel sees the same answer it does. */
	async function act(work: Promise<unknown>) {
		panel = null;
		groupPanel = null;
		error = null;
		try {
			await work;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		await bar.refresh();
	}

	function removeFolder(id: string) {
		// The folder, not what was written into it — the entries stay and their
		// tags go back in the unassigned pool.
		if (!confirm('Delete this folder? Its entries stay in the log.')) return;
		// Leaving the folder you are reading is the one case that has to
		// navigate: every lens under this is a question about it.
		if (id === scope.folder) choose(null);
		act(deleteFolder(id));
	}

	async function submitNewFolder(event: SubmitEvent) {
		event.preventDefault();
		const name = newName.trim();
		if (!name) {
			creating = false;
			return;
		}
		try {
			// No tags passed, and the folder claims none of its own: a new folder
			// collects nothing until you point a tag at it. See `create_folder` in
			// `backend/capture/store.py`, which is where that was reversed once.
			const { folder: made } = await createFolder(name);
			// And it starts `running`, which is not an assumption about what you
			// meant — it is the only way the thing you just made is on the list you
			// made it from. The shelf drops albums with nothing in them this year
			// *unless* they are active.
			await patchFolder(made.id, { state: 'active' });
			newName = '';
			creating = false;
			error = null;
			await bar.refresh();
			// Straight into it: you made it in order to be in it.
			choose(made.id);
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	let dragging = $state<string | null>(null);
	let dropAt = $state<string | null>(null);

	function dropGroup(name: string, before: string | null) {
		const year = shelf?.year;
		dragging = null;
		dropAt = null;
		if (!shelf || !year) return;
		const next = reorderGroups(shelf.groups, name, before);
		if (!next) return;
		shelf.groups = next;
		act(orderGroups(year, next));
	}

	const STATE_WORD: Record<string, string> = { active: 'running', shipped: 'shipped' };
</script>

<!-- The backdrop. A press anywhere else is "not that one", which is the
     ordinary way out of a list you opened to choose from. -->
<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div class="fixed inset-0 z-[9500]" onclick={onclose}>
	<!-- Under the bar, at the bar's left edge, and no wider than it needs to be:
	     this is a list of names, and a panel the width of the screen would make
	     choosing one a journey across it. -->
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="absolute flex max-h-[min(70vh,560px)] w-[300px] flex-col bg-surface shadow-lg"
		style="left:{x}px;top:{y}px;animation:landing-fade-in 0.12s ease-out"
		onclick={(e) => e.stopPropagation()}
	>
		{#if error}
			<p class="shrink-0 px-4 pt-3 text-[12px] text-error">{error}</p>
		{/if}

		<div data-sort-list="picker-groups" class="flex min-h-0 flex-1 flex-col overflow-y-auto py-2">
			{#snippet row(a: Album)}
				{@const on = a.id === scope.folder}
				<button
					type="button"
					use:hold={(hx, hy) => (panel = { folder: a, x: hx, y: hy })}
					class="flex h-11 shrink-0 items-center gap-2.5 px-4 text-left transition-colors {on
						? 'accent-fill font-bold'
						: 'hover:bg-neutral-200'}"
					onclick={() => choose(a.id)}
				>
					<span
						aria-hidden="true"
						class="h-[9px] w-[9px] shrink-0"
						style="background:{on ? 'var(--color-ground)' : toRamp(a.color)}"
					></span>
					<span class="min-w-0 flex-1 truncate text-[14px]">{a.name}</span>
					{#if STATE_WORD[a.state] && !on}
						<span class="shrink-0 text-[10px] font-bold tracking-[0.1em] text-neutral-600 uppercase">
							{STATE_WORD[a.state]}
						</span>
					{/if}
					<span class="shrink-0 text-[12px] tabular-nums {on ? 'opacity-80' : 'text-neutral-600'}">
						{a.entry_count}
					</span>
				</button>
			{/snippet}

			<!-- Everything, which is a subject two of the four lenses can answer
			     about and the reading lens cannot — see the bar. -->
			<button
				type="button"
				class="flex h-11 shrink-0 items-center gap-2.5 px-4 text-left transition-colors {scope.folder ===
				null
					? 'accent-fill font-bold'
					: 'text-neutral-700 hover:bg-neutral-200'}"
				onclick={() => choose(null)}
			>
				<span
					aria-hidden="true"
					class="h-[9px] w-[9px] shrink-0"
					style="background:{scope.folder === null ? 'var(--color-ground)' : 'var(--color-accent)'}"
				></span>
				<span class="min-w-0 flex-1 truncate text-[14px]">All folders</span>
				<span class="shrink-0 text-[12px] tabular-nums {scope.folder === null ? 'opacity-80' : 'text-neutral-600'}">
					{shelf?.entries ?? 0}
				</span>
			</button>

			<div class="mx-4 my-1 h-px shrink-0 bg-neutral-400"></div>

			{#each loose as a (a.id)}
				{@render row(a)}
			{/each}

			{#each sections as section (section.name)}
				{@const shut = folded.isShut(shelf?.year ?? null, section.name)}
				<!-- Where a dragged heading would land. -->
				<div
					class="mx-4 h-[2px] shrink-0 transition-colors {dragging && dropAt === section.name
						? 'bg-accent'
						: 'bg-transparent'}"
				></div>
				<button
					type="button"
					class="group/head mt-2 flex h-8 w-full shrink-0 items-center gap-2 px-4 text-left transition-opacity {dragging ===
					section.name
						? 'opacity-50'
						: ''}"
					aria-expanded={!shut}
					use:sortable={{
						key: section.name,
						list: 'picker-groups',
						onhold: (hx, hy) => (groupPanel = { name: section.name, x: hx, y: hy }),
						onpick: () => (dragging = section.name),
						onover: (before) => (dropAt = before),
						ondrop: (before) => dropGroup(section.name, before),
						oncancel: () => {
							dragging = null;
							dropAt = null;
						}
					}}
					onclick={() => folded.toggle(shelf?.year ?? null, section.name)}
				>
					<span
						class="inline-block text-[10px] leading-none text-neutral-600 transition-transform duration-150 group-hover/head:text-ink {shut
							? ''
							: 'rotate-90'}"
					>
						▶
					</span>
					<span
						class="min-w-0 flex-1 truncate text-[10px] font-bold tracking-[0.18em] text-neutral-600 uppercase transition-colors group-hover/head:text-ink"
					>
						{section.name}
					</span>
					<span class="shrink-0 text-[11px] text-neutral-600 tabular-nums">
						{section.albums.length}
					</span>
				</button>
				{#if !shut}
					{#each section.albums as a (a.id)}
						{@render row(a)}
					{/each}
				{/if}
			{/each}

			{#if dragging && dropAt === null && sections.length}
				<div class="mx-4 h-[2px] shrink-0 bg-accent"></div>
			{/if}

			{#if shelf && shelf.unfiled > 0}
				<button
					type="button"
					class="mt-1 flex h-11 shrink-0 items-center gap-2.5 px-4 text-left transition-colors {scope.folder ===
					'unfiled'
						? 'accent-fill font-bold'
						: 'text-neutral-700 hover:bg-neutral-200'}"
					onclick={() => choose('unfiled')}
				>
					<span
						aria-hidden="true"
						class="h-[9px] w-[9px] shrink-0"
						style="background:{scope.folder === 'unfiled'
							? 'var(--color-ground)'
							: 'var(--color-neutral-500)'}"
					></span>
					<span class="min-w-0 flex-1 truncate text-[14px]">Unfiled</span>
					<span class="shrink-0 text-[12px] tabular-nums">{shelf.unfiled}</span>
				</button>
			{/if}
		</div>

		<!-- The only list left, so the only place a folder can be made. -->
		<div class="shrink-0 p-2" style="box-shadow:inset 0 1px 0 0 var(--color-neutral-400)">
			{#if creating}
				<form
					class="focus-pill flex h-11 items-center gap-2.5 px-3"
					style="box-shadow:inset 0 0 0 1px var(--color-accent-400)"
					onsubmit={submitNewFolder}
				>
					<!-- svelte-ignore a11y_autofocus -->
					<input
						autofocus
						bind:value={newName}
						placeholder="name it"
						aria-label="new folder name"
						class="min-w-0 flex-1 bg-transparent text-[14px] font-semibold placeholder:font-normal placeholder:text-neutral-600"
						onkeydown={(e) => {
							if (e.key === 'Escape') {
								creating = false;
								newName = '';
							}
						}}
					/>
					<span class="shrink-0 text-[11px] text-neutral-600">↵</span>
				</form>
			{:else}
				<button
					type="button"
					class="flex h-11 w-full items-center gap-2 px-3 text-[13px] text-neutral-700 transition-colors hover:text-ink"
					onclick={() => (creating = true)}
				>
					<span class="text-[15px] leading-none">+</span>
					New folder
				</button>
			{/if}
		</div>
	</div>
</div>

{#if panel}
	{@const open = panel}
	<FolderPanel
		x={open.x}
		y={open.y}
		folder={open.folder}
		{unassigned}
		onpatch={(change) => act(patchFolder(open.folder.id, change))}
		ondelete={() => removeFolder(open.folder.id)}
		onclose={() => (panel = null)}
		year={scope.year === 'all' ? null : scope.year}
		group={shelf?.albums.find((a) => a.id === open.folder.id)?.group ?? ''}
		groups={shelf?.groups ?? []}
		ongroup={(name) => act(setFolderGroup(open.folder.id, shelf?.year ?? '', name))}
	/>
{/if}

{#if groupPanel && shelf?.year}
	{@const held = groupPanel}
	{@const year = shelf.year}
	<GroupPanel
		x={held.x}
		y={held.y}
		name={held.name}
		{year}
		count={shelf.albums.filter((a) => a.group === held.name).length}
		onrename={(to) => act(renameGroup(year, held.name, to))}
		ondelete={() => act(deleteGroup(year, held.name))}
		onclose={() => (groupPanel = null)}
	/>
{/if}
