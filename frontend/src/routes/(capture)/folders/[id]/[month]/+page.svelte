<script lang="ts">
	/**
	 * One month of one album — the rung between the year and the day.
	 *
	 * The argument: the Log has a year (the shelf) and a project (the album) and
	 * then nothing until the individual day. Everything below the album is one
	 * unbroken scroll wearing a sticky label, which is why the album header
	 * still says AUGUST 2026 while you are reading last September, and why the
	 * month spine can only scroll rather than take you anywhere.
	 *
	 * A month is the missing rung. Twelve of them make a year readable as twelve
	 * objects instead of five hundred entries; the spine and the chapter list
	 * become navigation to a place rather than a scroll position; and the header
	 * is true by construction, because the screen *is* the month it names.
	 *
	 * The month opens with what it looked like — a contact strip of everything
	 * made in it — and then reads down in days. That order is the album screen's
	 * argument applied one level up: you recognise a stretch of your life by the
	 * pictures, and read the words once you have found it.
	 *
	 * Nothing new is stored and no endpoint was added: this is `/api/capture/album`
	 * for the year, cut by day key in the browser. Deliberate for now — a year is
	 * a few hundred entries and the cut is free, while a `?month=` on the read
	 * would be a second way to ask the same question. Move it into the read when
	 * a year stops fitting in one fetch, and not before.
	 */
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import AlbumSidebar from '$lib/trophic/AlbumSidebar.svelte';
	import LightDay from '$lib/trophic/LightDay.svelte';
	import Lightbox from '$lib/trophic/Lightbox.svelte';
	import MediaTile from '$lib/trophic/MediaTile.svelte';
	import MonthSpine from '$lib/trophic/MonthSpine.svelte';
	import TabPill from '$lib/trophic/TabPill.svelte';
	import {
		foldQuiet,
		groupDays,
		monthLabel,
		stretchLabel,
		stretchTally
	} from '$lib/trophic/log';
	import { logSettings } from '$lib/trophic/settings.svelte';
	import type { Shot } from '$lib/trophic/media';
	import Glyph from '$lib/trophic/Glyph.svelte';
	import {
		deleteGroup,
		getAlbum,
		getShelf,
		nameChapter,
		orderGroups,
		renameGroup,
		toggleLine,
		type AlbumView,
		type Chapter,
		type Entry,
		type Shelf
	} from '$lib/trophic/api';
	import ChapterPanel from '$lib/trophic/ChapterPanel.svelte';
	import GroupPanel from '$lib/trophic/GroupPanel.svelte';

	const id = $derived(page.params.id!);
	const month = $derived(page.params.month!); // `YYYY-MM`
	const folderId = $derived(id === 'unfiled' ? null : id);
	const year = $derived(month.slice(0, 4));

	let album = $state<AlbumView | null>(null);
	let shelf = $state<Shelf | null>(null);
	let collapsed = $state(false);
	let expanded = $state<Set<string>>(new Set());
	let lightbox = $state<{ shots: Shot[]; index: number } | null>(null);
	let loading = $state(true);
	/** The chapter panel, from a hold on one of the sidebar's rows. The chapter
	 *  list is the same component and the same rows on this screen as on the
	 *  album's, so a hold has to mean the same thing on both — a gesture that
	 *  works on one screen and draws the null ring on the next is worse than one
	 *  that was never offered. */
	let chapterPanel = $state<{ chapter: Chapter; x: number; y: number } | null>(null);
	/** And the group heading's, for the same reason: the sidebar is one object
	 *  and its rows answer a hold with the same thing on every screen it is on. */
	let groupPanel = $state<{ name: string; x: number; y: number } | null>(null);

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
		const [a, s] = await Promise.all([getAlbum(folderId, year), getShelf(year)]);
		album = a;
		shelf = s;
		loading = false;
	}

	const days = $derived(
		groupDays(album?.entries ?? []).filter((day) => day.key.slice(0, 7) === month)
	);
	const rows = $derived(foldQuiet(days, logSettings.mergeQuiet));
	/** Everything made this month, newest first — the strip at the top. */
	const shots = $derived(days.flatMap((d) => d.media));
	const lines = $derived(days.reduce((n, d) => n + d.entries.length, 0));

	/** Which months this album has anything in, for the arrows and the spine. */
	const monthsWithSomething = $derived(
		(album?.volumes ?? []).flatMap((n, i) => (n > 0 ? [i + 1] : []))
	);
	const index = $derived(monthsWithSomething.indexOf(Number(month.slice(5, 7))));

	const href = (m: number) =>
		`/folders/${id}/${year}-${String(m).padStart(2, '0')}`;

	function step(delta: number) {
		const next = monthsWithSomething[index + delta];
		if (next) goto(href(next));
	}

	/** Follow a thread from a month. It leaves for the album rather than
	 *  scrolling this screen: the other end of a thread is very often in a
	 *  different month, and the album is the screen that holds the whole year. */
	function jumpTo(entryId: string) {
		goto(`/folders/${id}?year=${year}&entry=${entryId}`);
	}

	async function onToggle(entry: Entry, line: number) {
		const { entry: updated } = await toggleLine(entry.id, line);
		if (album) album.entries = album.entries.map((e) => (e.id === updated.id ? updated : e));
	}

	function toggleStretch(key: string) {
		const next = new Set(expanded);
		if (next.has(key)) next.delete(key);
		else next.add(key);
		expanded = next;
	}

	/** The contact strip is the month at a glance, not the whole contact sheet:
	 *  twelve plates and a count, so the words are still above the fold. */
	const STRIP = 12;
</script>

<div class="flex h-dvh flex-col">
	<div class="flex shrink-0 items-center justify-between gap-6 px-[34px] pt-[22px] pb-[22px]">
		<div class="flex items-center gap-3.5">
			<TabPill />
			{#if collapsed}
				<button
					type="button"
					class="text-[16px] text-neutral-600 transition-colors hover:text-ink"
					aria-label="show the sidebar"
					onclick={() => (collapsed = false)}>›</button
				>
			{/if}
		</div>

		<div class="flex items-center gap-2 text-[12px] text-neutral-700">
			<button
				type="button"
				class="rounded-lg px-[11px] py-1.5 transition-colors hover:text-ink disabled:opacity-50"
				disabled={index <= 0}
				onclick={() => step(-1)}
			>
				← earlier
			</button>
			<button
				type="button"
				class="rounded-lg px-[11px] py-1.5 transition-colors hover:text-ink disabled:opacity-50"
				disabled={index === -1 || index >= monthsWithSomething.length - 1}
				onclick={() => step(1)}
			>
				later →
			</button>
		</div>
	</div>

	<div class="flex min-h-0 flex-1">
		{#if !collapsed}
			<AlbumSidebar
				{shelf}
				{album}
				{folderId}
				{year}
				{month}
				oncollapse={() => (collapsed = true)}
				onholdchapter={(chapter, x, y) => (chapterPanel = { chapter, x, y })}
				onholdgroup={(name, x, y) => (groupPanel = { name, x, y })}
				onorder={async (order) => {
					const on = shelf?.year;
					if (!on) return;
					// Applied here first, so the headings do not snap back to where
					// they were for the length of the round trip.
					shelf!.groups = order;
					await orderGroups(on, order);
					await refresh();
				}}
			/>
		{/if}

		<div class="min-w-0 flex-1 overflow-y-auto px-8 pb-16">
			{#if loading && !album}
				<p class="text-[13px] text-neutral-700">reading…</p>
			{:else if days.length === 0}
				<p class="text-[13px] text-neutral-700">nothing was written this month.</p>
			{:else}
				<div class="flex flex-col gap-[30px]">
					<!-- The month, named, with what it holds. -->
					<div class="flex items-baseline gap-4">
						<h1 class="text-[44px] leading-none font-extrabold tracking-[-0.035em]">
							{monthLabel(month).split(' ')[0]}
						</h1>
						<span class="flex items-center gap-3 text-[13px] text-neutral-700 tabular-nums">
							<span>{days.length} {days.length === 1 ? 'day' : 'days'}</span>
							<span class="flex items-center gap-1.5">
								<Glyph kind="entries" count={lines} />
								{lines}
							</span>
							{#if shots.length}
								<span class="flex items-center gap-1.5">
									<Glyph kind="media" count={shots.length} />
									{shots.length}
								</span>
							{/if}
						</span>
					</div>

					<!-- What the month looked like, before what was said about it. -->
					{#if shots.length}
						<div class="grid grid-cols-6 gap-1.5">
							{#each shots.slice(0, STRIP) as shot, i (shot.entry.id + ':' + shot.ref)}
								<MediaTile ref={shot.ref} onopen={() => (lightbox = { shots, index: i })} />
							{/each}
							{#if shots.length > STRIP}
								<button
									type="button"
									class="lift lift-sm flex aspect-square items-center justify-center rounded-[10px] bg-surface text-[13px] text-neutral-700 shadow-sm"
									onclick={() => (lightbox = { shots, index: STRIP })}
								>
									+{shots.length - STRIP}
								</button>
							{/if}
						</div>
					{/if}

					<div class="flex flex-col gap-3">
						{#each rows as row (row.kind === 'stretch' ? row.days[0].key : row.day.key)}
							{#if row.kind === 'day'}
								<LightDay
									day={row.day}
									onopen={(s, i) => (lightbox = { shots: s, index: i })}
									ontoggle={onToggle}
									onjump={jumpTo}
								/>
							{:else if expanded.has(row.days[0].key)}
								{#each row.days as day (day.key)}
									<LightDay
										{day}
										onopen={(s, i) => (lightbox = { shots: s, index: i })}
										ontoggle={onToggle}
									onjump={jumpTo}
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
								<button
									type="button"
									class="lift lift-sm flex items-baseline gap-4 rounded-[12px] bg-surface px-4 py-[13px] text-left text-[13px] text-neutral-700 shadow-sm"
									onclick={() => toggleStretch(row.days[0].key)}
								>
									<span class="font-semibold">{stretchLabel(row.days)}</span>
									<span>{stretchTally(row.days)}</span>
									<span class="ml-auto font-semibold">Expand ▾</span>
								</button>
							{/if}
						{/each}
					</div>
				</div>
			{/if}
		</div>

		{#if album}
			<MonthSpine
				volumes={album.volumes}
				live={Number(month.slice(5, 7)) - 1}
				onpick={(m) => goto(href(m + 1))}
			/>
		{/if}
	</div>
</div>

{#if chapterPanel}
	{@const held = chapterPanel}
	<ChapterPanel
		x={held.x}
		y={held.y}
		chapter={held.chapter}
		onrename={async (to, at) => {
			chapterPanel = null;
			await nameChapter(folderId, year, at, to);
			await refresh();
		}}
		onclose={() => (chapterPanel = null)}
	/>
{/if}

{#if groupPanel && shelf?.year}
	{@const held = groupPanel}
	{@const on = shelf.year}
	<GroupPanel
		x={held.x}
		y={held.y}
		name={held.name}
		year={on}
		count={shelf.albums.filter((a) => a.group === held.name).length}
		onrename={async (to) => {
			// The request first, the teardown second: clearing `groupPanel` tears
			// down this block and the `@const` bindings this call reads.
			const work = renameGroup(on, held.name, to);
			groupPanel = null;
			await work;
			await refresh();
		}}
		ondelete={async () => {
			const work = deleteGroup(on, held.name);
			groupPanel = null;
			await work;
			await refresh();
		}}
		onclose={() => (groupPanel = null)}
	/>
{/if}

{#if lightbox}
	{@const open = lightbox}
	<Lightbox
		shots={open.shots}
		index={open.index}
		onindex={(i) => (lightbox = { shots: open.shots, index: i })}
		onclose={() => (lightbox = null)}
	/>
{/if}
