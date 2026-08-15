<script lang="ts">
	/**
	 * The log — what you made, given back to you at the end of the day.
	 *
	 * This is a deliberate departure from the source, and from what this file
	 * used to be. The source's log is a date ruler down one side of a fixed
	 * 520px pane showing one day at a time; it was built for a text capture
	 * tool with no media in it, and against a folder of photographs and clips
	 * it is the wrong instrument — a narrow one-directional portal that cannot
	 * answer "how much is in here". Chronological order is the one thing it
	 * did well, and a scrolling feed does that too.
	 *
	 * So: a feed of days, newest first, each a contact sheet over its lines.
	 * Dates are a label now rather than a control. Navigation is scrolling,
	 * because that is what a journal is read with.
	 *
	 * Two reads, not one:
	 *   - `all` is a window on the newest entries, widened by `load more`.
	 *   - a folder chip is the *whole* folder, from `/folders/{id}`, because a
	 *     project read back should not stop at the edge of a window that was
	 *     sized for the unfiltered feed.
	 *
	 * The cumulative readings are still here, at the foot and folded away.
	 * They are true and they are drawn, never interpreted — they are just not
	 * what you open the log for.
	 */
	import DayBlock from '$lib/trophic/DayBlock.svelte';
	import FolderAssignMenu from '$lib/trophic/FolderAssignMenu.svelte';
	import Lightbox from '$lib/trophic/Lightbox.svelte';
	import { todayKey } from '$lib/trophic/day';
	import type { Shot } from '$lib/trophic/media';
	import {
		assignEntry,
		createFolder,
		getEntries,
		getFolder,
		getFolders,
		getVocab,
		toggleLine,
		type Entry,
		type Folder
	} from '$lib/trophic/api';

	/** One page of the unfiltered feed. Two hundred entries is months of this
	 *  journal; the day the number is wrong, `load more` is already there. */
	const PAGE = 200;

	let entries = $state<Entry[]>([]);
	let folders = $state<Folder[]>([]);
	let tagToFolder = $state<Record<string, string>>({});
	let cumulative = $state<{
		folders: { name: string; count: number }[];
		word_count: number;
		sentiments: { name: string; total: number; dow: number[] }[];
	} | null>(null);
	let error = $state<string | null>(null);

	let limit = $state(PAGE);
	let selectedFolder = $state<string | null>(null);
	let loading = $state(false);
	/** True while the window is smaller than what is on disk. */
	let more = $state(false);

	let lightbox = $state<{ shots: Shot[]; index: number } | null>(null);
	let assignMenu = $state<{ x: number; y: number; entry: Entry } | null>(null);

	let showReadings = $state(false);
	let activeSentiment = $state<string | null>(null);
	let pickerOpen = $state(false);

	let creating = $state(false);
	let newName = $state('');

	const today = todayKey();

	$effect(() => {
		try {
			showReadings = localStorage.getItem('trophic-show-readings') === '1';
			activeSentiment = localStorage.getItem('trophic-sentiment');
		} catch {
			/* ignore */
		}
		refreshFolders();
		getVocab()
			.then((v) => (tagToFolder = v.tag_to_folder))
			.catch(() => {});
		fetch(`/api/capture/cumulative?up_to=${today}`)
			.then((r) => (r.ok ? r.json() : null))
			.then((c) => (cumulative = c))
			.catch(() => {});
	});

	// The feed. Keyed on the two things that decide what it holds, so nothing
	// refetches when a checkbox is ticked or a menu opens.
	let lastKey = '';
	$effect(() => {
		const key = `${selectedFolder ?? ''}:${limit}`;
		if (key === lastKey) return;
		lastKey = key;
		load(selectedFolder, limit);
	});

	async function load(folderId: string | null, want: number) {
		loading = true;
		error = null;
		try {
			if (folderId) {
				entries = (await getFolder(folderId)).entries;
				more = false;
			} else {
				const page = (await getEntries({ limit: want })).entries;
				// A window that came back full is a window that cut something
				// off, and what it cut off is the *oldest* day — whose tally
				// would then be a lie. Drop that day and offer `load more`
				// instead of showing a day block that undercounts itself.
				more = page.length === want;
				entries = more ? page.filter((e) => e.day !== page[page.length - 1].day) : page;
			}
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		loading = false;
	}

	/** Which folders an entry resolves into: through its tags, or by hand. */
	function foldersOf(entry: Entry): Folder[] {
		const ids = new Set<string>(entry.manual_folders);
		for (const tag of entry.folders) {
			const id = tagToFolder[tag];
			if (id) ids.add(id);
		}
		return folders.filter((f) => ids.has(f.id));
	}

	const groups = $derived.by(() => {
		const map = new Map<string, Entry[]>();
		for (const e of entries) {
			if (!map.has(e.day)) map.set(e.day, []);
			map.get(e.day)!.push(e);
		}
		return [...map.entries()].sort((a, b) => b[0].localeCompare(a[0]));
	});

	function dayLabel(key: string): string {
		if (key === today) return 'today';
		const [y, m, d] = key.split('-').map(Number);
		const date = new Date(y, m - 1, d);
		const yesterday = new Date();
		yesterday.setDate(yesterday.getDate() - 1);
		if (date.toDateString() === yesterday.toDateString()) return 'yesterday';
		return date.toLocaleDateString(undefined, {
			weekday: 'short',
			day: 'numeric',
			month: 'short',
			// The year only once it stops being obvious, which is the only time
			// it carries information.
			year: y === new Date().getFullYear() ? undefined : 'numeric'
		});
	}

	/** Chips: what you are working on first, what is done last and dimmed. */
	const chips = $derived(
		[...folders]
			.filter((f) => f.entry_count > 0 || f.state === 'active')
			.sort((a, b) => {
				const rank = (f: Folder) => (f.state === 'active' ? 0 : f.state === 'shipped' ? 2 : 1);
				return rank(a) - rank(b) || b.entry_count - a.entry_count;
			})
	);

	async function refreshFolders() {
		try {
			folders = (await getFolders()).folders;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	async function onToggle(entry: Entry, line: number) {
		try {
			const { entry: updated } = await toggleLine(entry.id, line);
			entries = entries.map((e) => (e.id === updated.id ? updated : e));
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	async function refile(entry: Entry, folderId: string | null) {
		error = null;
		try {
			const { entry: updated } = await assignEntry(entry.id, folderId);
			entries = entries.map((e) => (e.id === updated.id ? updated : e));
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		await refreshFolders();
	}

	async function submitNewFolder(event: SubmitEvent) {
		event.preventDefault();
		const name = newName.trim();
		if (!name) return;
		newName = '';
		creating = false;
		error = null;
		try {
			await createFolder(name);
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		await refreshFolders();
	}

	function persist(key: string, value: string) {
		try {
			localStorage.setItem(key, value);
		} catch {
			/* ignore */
		}
	}

	const activeSentimentData = $derived(
		cumulative?.sentiments.find((s) => s.name === activeSentiment) ?? cumulative?.sentiments[0]
	);

	const DOW = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

	const selected = $derived(folders.find((f) => f.id === selectedFolder) ?? null);
	const shown = $derived(entries.length);
</script>

<svelte:window onclick={() => (pickerOpen = false)} />

<!-- The chip rail is the header. There is no title and no back link: the tab
     bar above says both, and repeating it a centimetre lower is furniture. -->
<header class="sticky top-0 z-30 bg-[#14100c] pt-3 pb-2">
	<div class="trophic-scrollbar-hide mx-auto flex w-full max-w-2xl gap-1.5 overflow-x-auto px-6 pb-1">
		<button
			type="button"
			class="shrink-0 rounded-full px-3 py-1.5 text-[11px] whitespace-nowrap transition-colors {selectedFolder ===
			null
				? 'bg-stone-200 text-stone-900'
				: 'bg-stone-900 text-stone-400 hover:bg-stone-800'}"
			onclick={() => (selectedFolder = null)}
		>
			all
		</button>
		{#each chips as f (f.id)}
			{@const on = selectedFolder === f.id}
			<button
				type="button"
				class="flex shrink-0 items-center gap-1.5 rounded-full px-3 py-1.5 text-[11px] whitespace-nowrap transition-colors {on
					? 'text-stone-900'
					: 'bg-stone-900 hover:bg-stone-800'} {f.state === 'shipped' && !on ? 'opacity-45' : ''}"
				style={on ? `background:${f.color}` : `color:${f.color}`}
				onclick={() => (selectedFolder = on ? null : f.id)}
			>
				{f.name}
				<span class="tabular-nums {on ? 'opacity-60' : 'opacity-50'}">{f.entry_count}</span>
			</button>
		{/each}
		<button
			type="button"
			class="shrink-0 rounded-full border border-dashed border-stone-800 px-3 py-1.5 text-[11px] whitespace-nowrap text-stone-600 transition-colors hover:border-stone-700 hover:text-stone-400"
			onclick={() => (creating = !creating)}
		>
			{creating ? 'cancel' : '+ folder'}
		</button>
	</div>
</header>

<main class="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-6 px-6 pb-24">
	{#if creating}
		<form class="flex items-baseline gap-3" onsubmit={submitNewFolder}>
			<!-- svelte-ignore a11y_autofocus -->
			<input
				autofocus
				bind:value={newName}
				placeholder="folder name"
				class="flex-1 border-b border-stone-700 bg-transparent py-2 text-sm text-stone-200 transition-colors focus:border-stone-500 focus:outline-none"
				style="caret-color:#e7e5e4"
				onkeydown={(e) => {
					if (e.key === 'Escape') creating = false;
				}}
			/>
			<button type="submit" class="text-[11px] text-stone-400 hover:text-stone-200">create</button>
		</form>
	{/if}

	{#if selected}
		<!-- Filtered: say what is being shown, and offer the folder's own page,
		     which is the same feed with a head on it. -->
		<div class="flex items-baseline justify-between text-[11px]">
			<span class="text-stone-500">
				{shown}
				{shown === 1 ? 'entry' : 'entries'} in <span style="color:{selected.color}"
					>{selected.name}</span
				>
			</span>
			<a href="/folders/{selected.id}" class="text-stone-500 hover:text-stone-300">open →</a>
		</div>
	{/if}

	{#if error}
		<p class="text-[11px] text-red-400">{error}</p>
	{/if}

	{#if groups.length === 0}
		<p class="pt-6 text-[11px] text-stone-500">
			{loading
				? 'reading…'
				: selected
					? 'nothing in this folder yet.'
					: 'capture something and it will be here.'}
		</p>
	{:else}
		<div class="flex flex-col gap-8">
			{#each groups as [day, list] (day)}
				<DayBlock
					{day}
					label={dayLabel(day)}
					entries={list}
					{foldersOf}
					onopen={(shots, index) => (lightbox = { shots, index })}
					ontoggle={onToggle}
					onassign={(entry, x, y) => (assignMenu = { x, y, entry })}
				/>
			{/each}
		</div>
	{/if}

	{#if more}
		<button
			type="button"
			class="self-center rounded-full border border-stone-800 px-5 py-2 text-[11px] text-stone-500 transition-colors hover:border-stone-700 hover:text-stone-300"
			onclick={() => (limit += PAGE)}
			disabled={loading}
		>
			{loading ? 'reading…' : 'load more'}
		</button>
	{/if}

	<!-- ── Readings ─────────────────────────────────────────────────────────
	     Stored and drawn, never interpreted. Folded away by default: they are
	     a thing you go and look at, not a thing you are shown. -->
	<div class="mt-4 border-t border-stone-900 pt-4">
		<button
			type="button"
			class="text-[10px] tracking-[0.15em] text-stone-600 uppercase transition-colors hover:text-stone-400"
			onclick={() => {
				showReadings = !showReadings;
				persist('trophic-show-readings', showReadings ? '1' : '0');
			}}
		>
			readings {showReadings ? '▾' : '▸'}
		</button>

		{#if showReadings && cumulative}
			<div class="mt-4 flex flex-col gap-5 text-[11px]">
				<span class="text-stone-500">{cumulative.word_count.toLocaleString()} words</span>

				{#if cumulative.folders.length > 0}
					{@const max = Math.max(...cumulative.folders.map((f) => f.count))}
					<div class="flex flex-col gap-1.5">
						{#each cumulative.folders as f (f.name)}
							<div class="flex items-center gap-2" title="{f.count} entries tagged <{f.name}>">
								<span class="w-24 shrink-0 truncate text-right" style="color:#60a5fa"
									>{`<${f.name}>`}</span
								>
								<div class="h-[6px] flex-1 overflow-hidden rounded-full bg-stone-800">
									<div
										class="h-full rounded-full transition-all duration-500"
										style="width:{(f.count / max) * 100}%;background:#60a5fa"
									></div>
								</div>
								<span class="w-6 shrink-0 text-right text-stone-500 tabular-nums">{f.count}</span>
							</div>
						{/each}
					</div>
				{/if}

				{#if activeSentimentData}
					{@const s = activeSentimentData}
					{@const peak = Math.max(...s.dow, 0.01)}
					<div class="flex flex-col gap-3">
						<div class="relative self-start">
							<button
								type="button"
								class="rounded bg-rose-500/15 px-2.5 py-1 text-[10px] tracking-wide text-rose-300 transition-colors hover:bg-rose-500/25"
								onclick={(e) => {
									e.stopPropagation();
									pickerOpen = !pickerOpen;
								}}
							>
								{`\\${s.name} ▾`}
							</button>
							{#if pickerOpen}
								<div
									class="absolute top-full left-0 z-50 mt-1 min-w-[120px] rounded border border-stone-700 bg-[#1b1613] py-1 shadow-lg"
								>
									{#each cumulative.sentiments as opt (opt.name)}
										<button
											type="button"
											class="w-full px-3 py-1.5 text-left text-[11px] transition-colors hover:bg-stone-800 {opt.name ===
											s.name
												? 'text-rose-300'
												: 'text-stone-400'}"
											onclick={() => {
												activeSentiment = opt.name;
												persist('trophic-sentiment', opt.name);
												pickerOpen = false;
											}}
										>
											{`\\${opt.name}`}<span class="ml-2 text-stone-600">{opt.total}</span>
										</button>
									{/each}
								</div>
							{/if}
						</div>
						<div class="flex justify-center py-1">
							<div class="flex items-end gap-3 pt-3" title="average \{s.name} per weekday">
								{#each s.dow as v, i (i)}
									<div class="flex flex-col items-center gap-1" style="width:20px">
										<span
											class="text-[9px] leading-none text-stone-500 tabular-nums"
											style="opacity:{v > 0 ? 1 : 0}"
										>
											{v % 1 === 0 ? v : v.toFixed(1)}
										</span>
										<div
											class="w-full rounded-t bg-rose-400/80 transition-all duration-500"
											style="height:{Math.max((v / peak) * 56, v > 0 ? 2 : 0)}px"
										></div>
										<span class="text-[8px] leading-none text-stone-600">{DOW[i]}</span>
									</div>
								{/each}
							</div>
						</div>
					</div>
				{/if}

				<a href="/mapping" class="text-stone-600 hover:text-stone-400">mapping →</a>
			</div>
		{/if}
	</div>
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

{#if assignMenu}
	{@const target = assignMenu.entry}
	<FolderAssignMenu
		x={assignMenu.x}
		y={assignMenu.y}
		{folders}
		current={target.manual_folders[0] ?? null}
		onselect={(folderId) => refile(target, folderId)}
		onclear={() => refile(target, null)}
		onclose={() => (assignMenu = null)}
	/>
{/if}
