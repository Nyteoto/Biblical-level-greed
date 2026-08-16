<script lang="ts">
	/**
	 * One album, one year — the screen this app is used on most.
	 *
	 * An album is a folder read through a single year. Nothing stores that
	 * pairing: `/api/capture/album` recomputes the entries, the twelve month
	 * volumes and the chapters from the day keys on every read, which is what
	 * makes "albums restart each year" a switch in Settings rather than a
	 * migration, and what makes remapping a tag re-cut this whole screen with
	 * nothing to backfill.
	 *
	 * **Reaching history must not cost scrolling.** The album list, the chapter
	 * list and the month spine are all constant-cost, and the year cap is what
	 * keeps the spine constant-*size*: twelve bars, whatever the project's age.
	 * Scrolling is for reading. If something here starts needing a scroll to
	 * reach rather than to read, it has gone backwards.
	 *
	 * The header is journal-first on purpose — the month and the week number,
	 * not the folder name. You are reading a stretch of your life that happens
	 * to be filed under a project, and the sidebar already says which. The name
	 * repeats in a small pill only because the sidebar collapses.
	 *
	 * Below the header the days are two shapes and no more: the newest day gets
	 * the photograph and the caption (`LeadDay`), and everything under it is a
	 * line with a date on it (`LightDay`), with runs of quiet days folded into
	 * a strip. The rules that decide which is which are in `log.ts`, where a
	 * local check in `verify:ui` can hold them to never losing an entry.
	 */
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import FolderAssignMenu from '$lib/trophic/FolderAssignMenu.svelte';
	import LeadDay from '$lib/trophic/LeadDay.svelte';
	import LightDay from '$lib/trophic/LightDay.svelte';
	import Lightbox from '$lib/trophic/Lightbox.svelte';
	import MediaTile from '$lib/trophic/MediaTile.svelte';
	import MonthSpine from '$lib/trophic/MonthSpine.svelte';
	import TabPill from '$lib/trophic/TabPill.svelte';
	import { todayKey } from '$lib/trophic/day';
	import { foldQuiet, groupDays, isoWeek, monthLabel, stretchLabel, stretchTally } from '$lib/trophic/log';
	import { logSettings } from '$lib/trophic/settings.svelte';
	import type { Shot } from '$lib/trophic/media';
	import {
		assignEntry,
		deleteFolder,
		getAlbum,
		getShelf,
		getUnassignedTags,
		patchFolder,
		toggleLine,
		type AlbumView,
		type Entry,
		type Shelf,
		type UnassignedTag
	} from '$lib/trophic/api';

	const id = $derived(page.params.id!);
	/** `unfiled` is an album you can open like any other and is not a folder. */
	const folderId = $derived(id === 'unfiled' ? null : id);
	const year = $derived(page.url.searchParams.get('year') ?? String(new Date().getFullYear()));

	let album = $state<AlbumView | null>(null);
	let shelf = $state<Shelf | null>(null);
	let unassigned = $state<UnassignedTag[]>([]);
	let error = $state<string | null>(null);
	let loading = $state(true);

	let collapsed = $state(false);
	let sheet = $state(false);
	let showReadings = $state(false);
	let options = $state(false);
	let renaming = $state(false);
	let renameValue = $state('');
	/** Which quiet stretches the user has opened, by their first day. */
	let expanded = $state<Set<string>>(new Set());

	let menu = $state<{ x: number; y: number; entry: Entry } | null>(null);
	let lightbox = $state<{ shots: Shot[]; index: number } | null>(null);
	let column = $state<HTMLElement | null>(null);

	const today = todayKey();
	const thisYear = String(new Date().getFullYear());

	$effect(() => {
		logSettings.hydrate();
	});

	let lastKey = '';
	$effect(() => {
		const key = `${id}:${year}`;
		if (key === lastKey) return;
		lastKey = key;
		refresh();
	});

	async function refresh() {
		loading = true;
		try {
			const [a, s, u] = await Promise.all([
				getAlbum(folderId, year),
				getShelf(year),
				getUnassignedTags()
			]);
			album = a;
			shelf = s;
			unassigned = u.tags;
			error = null;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		loading = false;
	}

	const days = $derived(groupDays(album?.entries ?? []));
	const rows = $derived(foldQuiet(days.slice(1), logSettings.mergeQuiet));
	const lead = $derived(days[0] ?? null);
	/** Every attachment in the album, newest first — the contact sheet. */
	const shots = $derived(days.flatMap((d) => d.media));

	const liveMonth = $derived(year === thisYear || year === 'all' ? new Date().getMonth() : -1);
	const previousYear = $derived(shelf?.previous?.year ?? null);

	const name = $derived(album?.folder?.name ?? 'Unfiled');
	/** The month the top of the column is in. The header is about where you
	 *  are in the year, not about the album, so it reads off the lead day. */
	const heading = $derived(lead ? monthLabel(lead.key) : '');

	/** Scroll to the newest day in a month. `days` is newest first, so the first
	 *  match is the top of that month — which is where the reading starts. */
	function jumpToMonth(month: number) {
		const mm = String(month + 1).padStart(2, '0');
		const target = days.find((d) => d.key.slice(5, 7) === mm);
		if (!target) return;
		// The day may be inside a collapsed quiet stretch, in which case there
		// is nothing on screen to scroll to. Open it first.
		const stretch = rows.find(
			(row) => row.kind === 'stretch' && row.days.some((d) => d.key === target.key)
		);
		if (stretch?.kind === 'stretch') expanded = new Set([...expanded, stretch.days[0].key]);
		requestAnimationFrame(() =>
			column
				?.querySelector(`[data-day="${target.key}"]`)
				?.scrollIntoView({ behavior: 'smooth', block: 'start' })
		);
	}

	function toTop() {
		column?.scrollTo({ top: 0, behavior: 'smooth' });
	}

	function toggleStretch(key: string) {
		const next = new Set(expanded);
		if (next.has(key)) next.delete(key);
		else next.add(key);
		expanded = next;
	}

	const albumHref = (target: string | null) => `/folders/${target ?? 'unfiled'}?year=${year}`;

	async function act(work: Promise<unknown>) {
		error = null;
		try {
			await work;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		lastKey = '';
		await refresh();
	}

	async function onToggle(entry: Entry, line: number) {
		try {
			const { entry: updated } = await toggleLine(entry.id, line);
			if (album) album.entries = album.entries.map((e) => (e.id === updated.id ? updated : e));
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	async function submitRename() {
		const next = renameValue.trim();
		renaming = false;
		if (!next || !folderId || next === album?.folder?.name) return;
		await act(patchFolder(folderId, { name: next }));
	}

	async function remove() {
		// The folder, not what was written into it — the entries stay and their
		// tags go back in the unassigned pool. Worth saying out loud, because
		// "delete" beside a wall of photographs reads worse than it is.
		if (!folderId) return;
		if (!confirm('Delete this album? Its entries stay in the log.')) return;
		try {
			await deleteFolder(folderId);
			await goto('/log');
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	const STATES: { value: string; label: string }[] = [
		{ value: '', label: 'open' },
		{ value: 'active', label: 'running' },
		{ value: 'shipped', label: 'shipped' }
	];
</script>

<svelte:window onclick={() => (options = false)} />

<div class="flex h-dvh">
	<!-- ── Sidebar ─────────────────────────────────────────────────────────
	     No border. Cards on the tinted ground, which is the rule everywhere in
	     this design: a group is a white surface, never a rule. Collapsing it is
	     why the album's name repeats in the header. -->
	{#if !collapsed}
		<aside class="flex w-[252px] shrink-0 flex-col overflow-y-auto py-6">
			<div class="mx-3 mb-[18px]">
				<TabPill compact />
			</div>

			<div class="flex items-baseline gap-[9px] px-[22px] pb-5">
				<span class="text-[22px] font-extrabold tracking-[-0.02em]">
					{year === 'all' ? 'All' : year}
				</span>
				<span class="text-[12px] text-neutral-700">
					{shelf?.albums.length ?? 0}
					{shelf?.albums.length === 1 ? 'album' : 'albums'}
				</span>
				<button
					type="button"
					class="ml-auto text-[16px] text-neutral-600 transition-colors hover:text-ink"
					aria-label="collapse the sidebar"
					onclick={() => (collapsed = true)}>‹</button
				>
			</div>

			<div class="mx-3 flex flex-col gap-0.5 rounded-[14px] bg-surface p-2 shadow-md">
				{#each shelf?.albums ?? [] as a (a.id)}
					{@const on = a.id === folderId}
					<a
						href={albumHref(a.id)}
						class="flex items-center gap-2.5 rounded-[10px] px-3 py-[9px] transition-colors {on
							? 'accent-fill'
							: a.state === 'shipped'
								? 'text-neutral-700 hover:bg-neutral-200'
								: 'hover:bg-neutral-200'}"
					>
						<span class="min-w-0 flex-1 truncate {on ? 'text-[15px] font-bold' : 'text-[14px]'}">
							{a.name}
						</span>
						{#if a.state === 'shipped' && !on}
							<span class="text-[10px] font-bold tracking-[0.1em] uppercase">shipped</span>
						{:else}
							<span class="text-[12px] tabular-nums {on ? 'opacity-85' : 'text-neutral-700'}">
								{a.entry_count}
							</span>
						{/if}
					</a>
				{/each}
				{#if shelf && shelf.unfiled > 0}
					<a
						href={albumHref(null)}
						class="flex items-center gap-2.5 rounded-[10px] px-3 py-[9px] transition-colors {folderId ===
						null
							? 'accent-fill'
							: 'text-neutral-700 hover:bg-neutral-200'}"
					>
						<span class="min-w-0 flex-1 truncate text-[14px]">Unfiled</span>
						<span class="text-[12px] tabular-nums">{shelf.unfiled}</span>
					</a>
				{/if}
			</div>

			<!-- Chapters: month runs the app named from the user's own commonest
			     tag or pattern inside each run. Derived on the read like
			     everything else — nothing here was typed as a chapter. -->
			{#if album && album.chapters.length > 0}
				<div
					class="px-[22px] pt-[26px] pb-2.5 text-[10px] font-bold tracking-[0.2em] text-neutral-600 uppercase"
				>
					Chapters
				</div>
				<div class="mx-3 flex flex-col gap-2">
					{#each album.chapters as chapter, i (chapter.name + chapter.range)}
						<button
							type="button"
							class="flex items-baseline gap-2.5 rounded-[12px] text-left {i === 0
								? 'bg-surface px-3.5 py-[11px] shadow-sm'
								: 'px-3.5 py-[9px]'}"
							onclick={() => jumpToMonth(chapter.last_month - 1)}
						>
							{#if i === 0}
								<span
									class="w-[3px] self-stretch rounded-[2px]"
									style="background:var(--gradient-spine)"
								></span>
							{/if}
							<span
								class="min-w-0 flex-1 truncate {i === 0
									? 'text-[14px] font-bold'
									: 'text-[14px] text-neutral-800'}"
							>
								{chapter.name}
							</span>
							<span class="shrink-0 text-[11px] text-neutral-700">{chapter.range}</span>
						</button>
					{/each}
				</div>
			{/if}

			<p class="mt-auto px-[22px] pt-4 text-[11px] leading-[1.5] text-neutral-700">
				Chapters are month runs the app named from your own tags.
			</p>
		</aside>
	{/if}

	<div class="flex min-w-0 flex-1 flex-col pt-6">
		<!-- ── Header ────────────────────────────────────────────────────────
		     Journal-first: the month and the week, then the album's name as a
		     small pill so a collapsed sidebar still says where you are. -->
		<div class="flex shrink-0 items-center justify-between px-[34px] pb-[22px]">
			<div class="flex items-baseline gap-3.5">
				{#if collapsed}
					<button
						type="button"
						class="text-[16px] text-neutral-600 transition-colors hover:text-ink"
						aria-label="show the sidebar"
						onclick={() => (collapsed = false)}>›</button
					>
				{/if}
				<span class="text-[12px] font-bold tracking-[0.22em] uppercase">{heading}</span>
				{#if lead}
					<span class="text-[12px] text-neutral-700">week {isoWeek(lead.key)}</span>
				{/if}

				<div class="relative">
					<button
						type="button"
						class="rounded-lg bg-surface px-[9px] py-1 text-[12px] text-neutral-700 shadow-sm transition-shadow hover:shadow-md"
						title="rename, ship or delete this album"
						onclick={(e) => {
							e.stopPropagation();
							options = !options;
						}}
					>
						{name}
					</button>

					<!-- Everything that changes the *folder* rather than the view.
					     Behind the name because the name is what it is about, and
					     because the redesign gave these no home of their own —
					     dropping them would have quietly removed working features. -->
					{#if options && album?.folder}
						{@const folder = album.folder}
						<!-- svelte-ignore a11y_click_events_have_key_events -->
						<!-- svelte-ignore a11y_no_static_element_interactions -->
						<div
							class="absolute top-full left-0 z-50 mt-2 flex w-[290px] flex-col gap-3 rounded-[14px] bg-surface p-4 shadow-lg"
							style="animation:landing-fade-in 0.15s ease-out"
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
										class="w-full rounded-lg bg-neutral-200 px-3 py-2 text-[14px] focus:outline-none"
										onkeydown={(e) => {
											if (e.key === 'Escape') renaming = false;
										}}
									/>
								</form>
							{:else}
								<button
									type="button"
									class="text-left text-[14px] font-semibold"
									onclick={() => {
										renameValue = folder.name;
										renaming = true;
									}}
								>
									{folder.name}
									<span class="ml-2 text-[12px] font-normal text-neutral-700">rename</span>
								</button>
							{/if}

							<!-- The lifecycle. Three states and no taxonomy: the empty
							     one is the default, and a folder never marked is an
							     interest rather than a project. -->
							<div class="flex gap-0.5 rounded-[9px] bg-neutral-200 p-[3px]">
								{#each STATES as s (s.value)}
									<button
										type="button"
										class="flex-1 rounded-[7px] px-2.5 py-[5px] text-[12px] transition-colors {folder.state ===
										s.value
											? 'bg-surface font-bold shadow-sm'
											: 'font-semibold text-neutral-700'}"
										onclick={() => act(patchFolder(folder.id, { state: s.value }))}
									>
										{s.label}
									</button>
								{/each}
							</div>

							<div class="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-[12px]">
								{#each folder.tags as tag (tag)}
									<button
										type="button"
										class="font-mono transition-colors hover:text-accent-700"
										style="color:var(--color-accent-700)"
										title="click to unmap"
										onclick={() => act(patchFolder(folder.id, { remove_tags: [tag] }))}
									>
										{`<${tag}>`}
									</button>
								{:else}
									<span class="text-neutral-700">no tags point here yet</span>
								{/each}
							</div>

							{#if unassigned.length > 0}
								<div class="flex flex-wrap gap-2 rounded-[10px] bg-neutral-200 p-2.5 text-[12px]">
									{#each unassigned.slice(0, 8) as tag (tag.tag)}
										<button
											type="button"
											class="font-mono transition-colors hover:opacity-70"
											style="color:var(--color-neutral-800)"
											title="point this tag here"
											onclick={() => act(patchFolder(folder.id, { add_tags: [tag.tag] }))}
										>
											{`<${tag.tag}>`}<span class="ml-1 text-neutral-700">×{tag.count}</span>
										</button>
									{/each}
								</div>
							{/if}

							<button
								type="button"
								class="self-start text-[12px] font-semibold text-accent-700"
								onclick={remove}
							>
								Delete this album
							</button>
						</div>
					{/if}
				</div>
			</div>

			<div class="flex items-center gap-4 text-[12px] text-neutral-700">
				{#if shots.length > 1}
					<button
						type="button"
						class="transition-colors hover:text-ink {sheet ? 'text-ink' : ''}"
						onclick={() => (sheet = !sheet)}
					>
						Contact sheet
					</button>
				{/if}
				{#if album && album.sentiments.length > 0}
					<button
						type="button"
						class="transition-colors hover:text-ink {showReadings ? 'text-ink' : ''}"
						onclick={() => (showReadings = !showReadings)}
					>
						Readings
					</button>
				{/if}
				<button
					type="button"
					class="rounded-lg bg-surface px-[11px] py-1.5 font-semibold text-ink shadow-sm transition-shadow hover:shadow-md"
					onclick={toTop}
				>
					Today ↑
				</button>
			</div>
		</div>

		<div class="flex min-h-0 flex-1">
			<div bind:this={column} class="min-w-0 flex-1 overflow-y-auto px-8 pb-16">
				{#if error}
					<p class="pb-4 text-[12px] text-accent-700">{error}</p>
				{/if}

				{#if loading && !album}
					<p class="text-[13px] text-neutral-700">reading…</p>
				{:else if days.length === 0}
					<p class="text-[13px] text-neutral-700">capture something and it will be here.</p>
				{:else if sheet}
					<!-- Words off. Everything ever made in here, densest possible —
					     the thing the ruler this replaced could never do. -->
					<div class="grid grid-cols-6 gap-1.5">
						{#each shots as shot, i (shot.entry.id + ':' + shot.ref)}
							<MediaTile ref={shot.ref} onopen={() => (lightbox = { shots, index: i })} />
						{/each}
					</div>
				{:else}
					<div class="flex flex-col gap-[34px]">
						{#if lead}
							<LeadDay
								day={lead}
								today={lead.key === today}
								onopen={(s, index) => (lightbox = { shots: s, index })}
								ontoggle={onToggle}
								onassign={(entry, x, y) => (menu = { x, y, entry })}
							/>
						{/if}

						<div class="flex flex-col gap-3">
							{#each rows as row (row.kind === 'stretch' ? row.days[0].key : row.day.key)}
								{#if row.kind === 'day'}
									<LightDay
										day={row.day}
										onopen={(s, index) => (lightbox = { shots: s, index })}
										ontoggle={onToggle}
										onassign={(entry, x, y) => (menu = { x, y, entry })}
									/>
								{:else if expanded.has(row.days[0].key)}
									{#each row.days as day (day.key)}
										<LightDay
											{day}
											onopen={(s, index) => (lightbox = { shots: s, index })}
											ontoggle={onToggle}
											onassign={(entry, x, y) => (menu = { x, y, entry })}
										/>
									{/each}
									<button
										type="button"
										class="self-start text-[12px] font-semibold text-neutral-700 transition-colors hover:text-ink"
										onclick={() => toggleStretch(row.days[0].key)}
									>
										Collapse ▴
									</button>
								{:else}
									<!-- A merge, never a hide: the strip says how many lines
									     it is holding and expands into exactly the rows it
									     replaced. -->
									<button
										type="button"
										class="lift lift-sm flex items-baseline gap-4 rounded-[12px] bg-surface px-4 py-[13px] text-left text-neutral-700 shadow-sm"
										onclick={() => toggleStretch(row.days[0].key)}
									>
										<span class="w-[92px] shrink-0 text-[13px] font-semibold">
											{stretchLabel(row.days)}
										</span>
										<span class="flex-1 text-[14px]">{stretchTally(row.days)}</span>
										<span class="text-[12px] font-semibold">Expand ▾</span>
									</button>
								{/if}
							{/each}
						</div>

						<!-- The album's sentiment counts. Stored and drawn, never
						     interpreted — a reading, not a verdict. -->
						{#if showReadings && album}
							{@const max = Math.max(...album.sentiments.map((s) => s.count), 1)}
							<div class="flex max-w-[420px] flex-col gap-2 rounded-[16px] bg-surface p-4 shadow-md">
								{#each album.sentiments as s (s.name)}
									<div class="flex items-center gap-3 text-[12px]">
										<span
											class="w-24 shrink-0 truncate text-right font-mono"
											style="color:var(--color-accent-700)"
										>
											{`\\${s.name}`}
										</span>
										<div class="h-[7px] flex-1 overflow-hidden rounded-[4px] bg-neutral-200">
											<div
												class="h-full rounded-[4px]"
												style="width:{(s.count / max) * 100}%;background:var(--gradient-accent)"
											></div>
										</div>
										<span class="w-6 shrink-0 text-right text-neutral-700 tabular-nums">
											{s.count}
										</span>
									</div>
								{/each}
							</div>
						{/if}
					</div>
				{/if}
			</div>

			{#if album && !sheet}
				<MonthSpine
					volumes={album.volumes}
					live={liveMonth}
					{previousYear}
					onpick={jumpToMonth}
				/>
			{/if}
		</div>
	</div>
</div>

{#if lightbox}
	{@const open = lightbox}
	<Lightbox
		shots={open.shots}
		index={open.index}
		onindex={(index) => (lightbox = { shots: open.shots, index })}
		onclose={() => (lightbox = null)}
	/>
{/if}

{#if menu && shelf}
	{@const target = menu.entry}
	<FolderAssignMenu
		x={menu.x}
		y={menu.y}
		folders={shelf.albums}
		current={target.manual_folders[0] ?? null}
		onselect={(target_id) => act(assignEntry(target.id, target_id))}
		onclear={() => act(assignEntry(target.id, null))}
		onclose={() => (menu = null)}
	/>
{/if}
