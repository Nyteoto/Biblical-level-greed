<script lang="ts">
	/**
	 * One folder, read back as the case study it turned into.
	 *
	 * The tag chips are the folder's definition, not a summary of it — every
	 * entry below is here because of one of them, or because it was filed by
	 * hand. `+ assign` opens the unclaimed tags inline so a folder can be
	 * widened from the place you noticed it was too narrow, which is why that
	 * shortcut exists rather than a trip to mapping.
	 *
	 * Everything below the head is the log's own rendering, scoped to this
	 * folder: same day blocks, same tiles, same lightbox. That is deliberate —
	 * a project is not a different kind of reading, it is the same reading with
	 * the rest of life filtered out, and it should not feel like another screen.
	 *
	 * Two things are only here. The **cover** is the folder's most recent media,
	 * full width: a project is recognised by the last thing you made in it, not
	 * by its name. The **contact sheet** drops the words and shows nothing but
	 * media at the densest the screen allows, which is how you scan months of
	 * something at once — the thing the ruler this replaced could never do.
	 */
	import { page } from '$app/state';
	import DayBlock from '$lib/trophic/DayBlock.svelte';
	import FolderAssignMenu from '$lib/trophic/FolderAssignMenu.svelte';
	import Lightbox from '$lib/trophic/Lightbox.svelte';
	import MediaTile from '$lib/trophic/MediaTile.svelte';
	import { todayKey } from '$lib/trophic/day';
	import { mediaUrl, mediaViewUrl } from '$lib/trophic/api';
	import { isVideo, type Shot } from '$lib/trophic/media';
	import {
		assignEntry,
		deleteFolder,
		getFolder,
		getFolders,
		getUnassignedTags,
		patchFolder,
		toggleLine,
		type Entry,
		type Folder,
		type FolderDetail,
		type UnassignedTag
	} from '$lib/trophic/api';
	import { goto } from '$app/navigation';

	const id = $derived(page.params.id!);

	let detail = $state<FolderDetail | null>(null);
	let folders = $state<Folder[]>([]);
	let unassigned = $state<UnassignedTag[]>([]);
	let error = $state<string | null>(null);
	let showAssign = $state(false);
	let sheet = $state(false);
	let menu = $state<{ x: number; y: number; entry: Entry } | null>(null);
	let lightbox = $state<{ shots: Shot[]; index: number } | null>(null);
	let options = $state(false);
	let renaming = $state(false);
	let renameValue = $state('');

	const today = todayKey();

	async function refresh() {
		try {
			const [d, f, u] = await Promise.all([getFolder(id), getFolders(), getUnassignedTags()]);
			detail = d;
			folders = f.folders;
			unassigned = u.tags;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	$effect(() => {
		void id;
		refresh();
	});

	const entries = $derived(detail?.entries ?? []);

	/** Every attachment in the folder, newest first — the contact sheet, and
	 *  the pool the cover is drawn from. */
	const shots = $derived(
		entries.flatMap((entry) => (entry.media ?? []).map((ref) => ({ ref, entry })))
	);

	const groups = $derived.by(() => {
		const map = new Map<string, Entry[]>();
		for (const e of entries) {
			if (!map.has(e.day)) map.set(e.day, []);
			map.get(e.day)!.push(e);
		}
		return [...map.entries()].sort((a, b) => b[0].localeCompare(a[0]));
	});

	/** `11 days · 3 Mar → 14 Mar`. Days worked in, not days elapsed: a project
	 *  you touched on eleven days over a year is eleven days of work, and the
	 *  calendar distance between the ends says nothing about it. */
	const stat = $derived.by(() => {
		if (groups.length === 0) return null;
		const days = groups.map(([day]) => day);
		const first = days[days.length - 1];
		const last = days[0];
		const short = (key: string) => {
			const [y, m, d] = key.split('-').map(Number);
			return new Date(y, m - 1, d).toLocaleDateString(undefined, {
				day: 'numeric',
				month: 'short',
				year: y === new Date().getFullYear() ? undefined : 'numeric'
			});
		};
		const range = first === last ? short(last) : `${short(first)} → ${short(last)}`;
		return `${days.length} ${days.length === 1 ? 'day' : 'days'} · ${range}`;
	});

	function dayLabel(key: string): string {
		if (key === today) return 'today';
		const [y, m, d] = key.split('-').map(Number);
		return new Date(y, m - 1, d).toLocaleDateString(undefined, {
			weekday: 'short',
			day: 'numeric',
			month: 'short',
			year: y === new Date().getFullYear() ? undefined : 'numeric'
		});
	}

	const STATES: { value: string; label: string }[] = [
		{ value: '', label: 'open' },
		{ value: 'active', label: 'active' },
		{ value: 'shipped', label: 'shipped' }
	];

	async function act(work: Promise<unknown>) {
		error = null;
		try {
			await work;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		await refresh();
	}

	async function onToggle(entry: Entry, line: number) {
		try {
			const { entry: updated } = await toggleLine(entry.id, line);
			if (detail) {
				detail.entries = detail.entries.map((e) => (e.id === updated.id ? updated : e));
			}
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	async function submitRename() {
		const name = renameValue.trim();
		renaming = false;
		if (!name || name === detail?.folder.name) return;
		await act(patchFolder(id, { name }));
	}

	async function remove() {
		// The folder, not what was written into it — the entries stay and their
		// tags go back in the unassigned pool. Worth saying out loud, because
		// "delete" beside a wall of photographs reads worse than it is.
		if (!confirm('Delete this folder? Its entries stay in the log.')) return;
		try {
			await deleteFolder(id);
			await goto('/log');
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	const cover = $derived(shots[0] ?? null);
</script>

<svelte:window onclick={() => (options = false)} />

<header class="sticky top-0 z-30 bg-[#14100c] py-4 text-[11px] tracking-wide text-stone-500">
	<div class="mx-auto flex w-full max-w-2xl items-center justify-between px-6">
		<a href="/log" class="transition-colors hover:text-stone-300">← log</a>
		<div class="relative">
			<button
				type="button"
				class="px-2 transition-colors hover:text-stone-300"
				aria-label="folder options"
				onclick={(e) => {
					e.stopPropagation();
					options = !options;
				}}
			>
				···
			</button>
			{#if options}
				<!-- No stopPropagation: both items close the menu themselves, so
				     letting the click reach the window costs nothing. -->
				<div
					class="absolute top-full right-0 z-50 mt-1 flex min-w-[130px] flex-col rounded border border-stone-700 bg-[#1b1613] py-1.5 text-left shadow-xl"
				>
					<button
						type="button"
						class="px-4 py-2 text-left text-[12px] text-stone-300 transition-colors hover:bg-stone-800 hover:text-stone-100"
						onclick={() => {
							renameValue = detail?.folder.name ?? '';
							renaming = true;
						}}
					>
						rename
					</button>
					<button
						type="button"
						class="px-4 py-2 text-left text-[12px] text-red-400 transition-colors hover:bg-stone-800 hover:text-red-300"
						onclick={remove}
					>
						delete
					</button>
				</div>
			{/if}
		</div>
	</div>
</header>

<main class="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-6 pb-24">
	{#if error}
		<p class="text-[11px] text-red-400">{error}</p>
	{/if}

	{#if detail}
		{@const folder = detail.folder}

		{#if cover}
			<!-- The last thing made in here, at the top. Clipped to a band rather
			     than shown whole: it is a way in, not the photograph itself. -->
			<button
				type="button"
				class="-mx-6 block h-40 overflow-hidden bg-stone-900 sm:mx-0 sm:h-48 sm:rounded"
				onclick={() => (lightbox = { shots, index: 0 })}
				aria-label="open the most recent"
			>
				{#if isVideo(cover.ref)}
					<img src={mediaViewUrl(cover.ref)} alt="" class="h-full w-full object-cover opacity-90" />
				{:else}
					<img
						src={mediaViewUrl(cover.ref)}
						alt=""
						onerror={(e) => ((e.currentTarget as HTMLImageElement).src = mediaUrl(cover.ref))}
						class="h-full w-full object-cover"
					/>
				{/if}
			</button>
		{/if}

		<div class="flex flex-col gap-3">
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
						class="w-full border-b border-stone-600 bg-transparent py-1 text-xl text-stone-100 focus:border-stone-400 focus:outline-none"
						style="caret-color:#fafaf9"
						onblur={submitRename}
						onkeydown={(e) => {
							if (e.key === 'Escape') renaming = false;
						}}
					/>
				</form>
			{:else}
				<h1 class="flex items-center gap-2.5 text-xl text-stone-100">
					<span class="h-2.5 w-2.5 shrink-0 rounded-full" style="background:{folder.color}"></span>
					{folder.name}
				</h1>
			{/if}

			<div class="flex flex-wrap items-center gap-x-3 gap-y-2 text-[11px] text-stone-500">
				{#if stat}
					<span>{stat}</span>
					<span class="text-stone-700">·</span>
				{/if}
				<!-- The lifecycle. Three states and no taxonomy: the empty one is
				     the default, and a folder never marked is an interest rather
				     than a project. -->
				<span class="flex items-center gap-1">
					{#each STATES as s (s.value)}
						<button
							type="button"
							class="rounded-full px-2 py-0.5 transition-colors {folder.state === s.value
								? 'bg-stone-200 text-stone-900'
								: 'text-stone-600 hover:text-stone-400'}"
							onclick={() => act(patchFolder(id, { state: s.value }))}
						>
							{s.label}
						</button>
					{/each}
				</span>
				{#if shots.length > 1}
					<span class="text-stone-700">·</span>
					<button
						type="button"
						class="transition-colors hover:text-stone-300 {sheet ? 'text-stone-300' : ''}"
						onclick={() => (sheet = !sheet)}
					>
						contact sheet {sheet ? '▾' : '▸'}
					</button>
				{/if}
			</div>

			<div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
				{#each folder.tags as tag (tag)}
					<button
						type="button"
						class="text-blue-400/80 transition-colors hover:text-red-400"
						title="click to unassign"
						onclick={() => act(patchFolder(id, { remove_tags: [tag] }))}
					>
						{`<${tag}>`}
					</button>
				{:else}
					<span class="text-stone-500">no tags point here yet</span>
				{/each}
				<button
					type="button"
					class="ml-1 text-stone-500 transition-colors hover:text-stone-300"
					onclick={() => (showAssign = !showAssign)}
				>
					{showAssign ? 'done' : '+ assign'}
				</button>
			</div>

			{#if showAssign}
				<div
					class="flex flex-wrap gap-3 rounded-lg border border-stone-800 bg-stone-900/40 p-3 text-[11px]"
				>
					{#each unassigned as tag (tag.tag)}
						<button
							type="button"
							class="text-blue-400 transition-colors hover:text-blue-200"
							onclick={() => act(patchFolder(id, { add_tags: [tag.tag] }))}
						>
							{`<${tag.tag}>`}<span class="ml-1 text-stone-600">×{tag.count}</span>
						</button>
					{:else}
						<span class="text-stone-500">no unassigned tags</span>
					{/each}
				</div>
			{/if}
		</div>

		{#if entries.length === 0}
			<p class="text-[11px] text-stone-500">nothing here yet — capture with these tags to fill it.</p>
		{:else if sheet}
			<!-- Words off. Everything ever made in here, densest possible. -->
			<div class="grid grid-cols-4 gap-1 sm:grid-cols-6">
				{#each shots as shot, i (shot.entry.id + ':' + shot.ref)}
					<MediaTile ref={shot.ref} onopen={() => (lightbox = { shots, index: i })} />
				{/each}
			</div>
		{:else}
			<div class="flex flex-col gap-8">
				{#each groups as [day, list] (day)}
					<DayBlock
						{day}
						label={dayLabel(day)}
						entries={list}
						onopen={(dayShots, index) => (lightbox = { shots: dayShots, index })}
						ontoggle={onToggle}
						onassign={(entry, x, y) => (menu = { x, y, entry })}
					/>
				{/each}
			</div>
		{/if}

		<!-- The folder's sentiment counts. A reading, not a verdict. -->
		{#if detail.sentiments.length > 0}
			{@const max = Math.max(...detail.sentiments.map((s) => s.count))}
			<div class="mt-4 flex flex-col gap-1.5 border-t border-stone-900 pt-4 text-[11px]">
				{#each detail.sentiments as s (s.name)}
					<div class="flex items-center gap-2" title="{s.count} entries here with \{s.name}">
						<span class="w-24 shrink-0 truncate text-right" style="color:#fb7185"
							>{`\\${s.name}`}</span
						>
						<div class="h-[6px] flex-1 overflow-hidden rounded-full bg-stone-800">
							<div
								class="h-full rounded-full transition-all duration-500"
								style="width:{(s.count / max) * 100}%;background:#fb7185"
							></div>
						</div>
						<span class="w-6 shrink-0 text-right text-stone-500 tabular-nums">{s.count}</span>
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</main>

{#if lightbox}
	{@const open = lightbox}
	<Lightbox
		shots={open.shots}
		index={open.index}
		onindex={(index) => (lightbox = { shots: open.shots, index })}
		onclose={() => (lightbox = null)}
	/>
{/if}

{#if menu}
	{@const target = menu.entry}
	<FolderAssignMenu
		x={menu.x}
		y={menu.y}
		{folders}
		current={target.manual_folders[0] ?? null}
		onselect={(folderId) => act(assignEntry(target.id, folderId))}
		onclear={() => act(assignEntry(target.id, null))}
		onclose={() => (menu = null)}
	/>
{/if}
