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
	 *
	 * **This screen is the year, and a month is one level below it** — see
	 * `[month]/+page.svelte`. The spine and the chapter list open a month rather
	 * than scrolling the column to one, which is what makes the month a place
	 * you can be rather than a position you can reach. This screen keeps the
	 * whole year in one column because that is how you read back a project you
	 * are in the middle of; the month is for finding your way to a stretch of it.
	 */
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import FolderAssignMenu from '$lib/trophic/FolderAssignMenu.svelte';
	import LeadDay from '$lib/trophic/LeadDay.svelte';
	import LightDay from '$lib/trophic/LightDay.svelte';
	import Lightbox from '$lib/trophic/Lightbox.svelte';
	import MediaTile from '$lib/trophic/MediaTile.svelte';
	import AlbumSidebar from '$lib/trophic/AlbumSidebar.svelte';
	import MonthSpine from '$lib/trophic/MonthSpine.svelte';
	import Segmented from '$lib/trophic/Segmented.svelte';
	import TabPill from '$lib/trophic/TabPill.svelte';
	import { todayKey } from '$lib/trophic/day';
	import { albumWeek, foldQuiet, groupDays, stretchLabel, stretchTally } from '$lib/trophic/log';
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
		type Folder,
		type Shelf,
		type UnassignedTag
	} from '$lib/trophic/api';
	import { lastAlbum } from '$lib/trophic/lastalbum.svelte';
	import FolderPanel from '$lib/trophic/FolderPanel.svelte';
	import OverviewCard from '$lib/trophic/OverviewCard.svelte';
	import HoldMenu from '$lib/trophic/HoldMenu.svelte';

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
	/** The properties panel, opened by holding a folder in the sidebar. */
	let panel = $state<{ folder: Folder; x: number; y: number } | null>(null);
	/** Whether the overview has taken the day column's place. Reset when the
	 *  album changes: it is a property of reading *this* folder, not a mode. */
	let overviewOpen = $state(false);
	/** A held photograph, and what can be done with it. One option today; it is
	 *  a menu rather than a direct action because "hold to silently change
	 *  something" is not a gesture anyone should have to discover twice. */
	let heldMedia = $state<{ ref: string; x: number; y: number } | null>(null);
	/** The overview's own picture, held. Its only option is removal, which is
	 *  why it had a standing button until the gesture could carry it. */
	let heldPicture = $state<{ x: number; y: number } | null>(null);
	$effect(() => {
		void id;
		void year;
		overviewOpen = false;
	});
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

	// Remember where the reading is, so the Log tab can flip back to it from the
	// shelf. `id` and not `folderId`, because `unfiled` is an album you can be
	// returned to like any other — it is just not a folder.
	$effect(() => {
		lastAlbum.remember(id, year);
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
	/** The spine and the chapter list open the month. They used to scroll the
	 *  column to it, which was the tell that a month was not a thing you could
	 *  be in — you could reach one, but the header went on naming the newest
	 *  day's month however far back you read. */
	function jumpToMonth(month: number) {
		goto(`/folders/${id}/${year}-${String(month + 1).padStart(2, '0')}`);
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

	async function remove(id: string) {
		// The folder, not what was written into it — the entries stay and their
		// tags go back in the unassigned pool. Worth saying out loud, because
		// "delete" beside a wall of photographs reads worse than it is.
		if (!confirm('Delete this folder? Its entries stay in the log.')) return;
		panel = null;
		try {
			await deleteFolder(id);
			// Leaving the album you were reading is the only case that has to
			// navigate; deleting another one just refreshes the shelf beside it.
			if (id === folderId) await goto('/log?shelf');
			else {
				lastKey = '';
				await refresh();
			}
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

</script>


<div class="flex h-dvh flex-col">
	<!-- ── Header ────────────────────────────────────────────────────────
	     One row across the whole page, above the sidebar rather than beside
	     it, so the nav pill is in the same corner here as on every other
	     screen. It used to sit at the top of the sidebar, which put it in a
	     third place — and a navigation control that moves is one you have to
	     look for every time.

	     After the pill it is journal-first: the month and the week, then the
	     album's name as a small pill so a collapsed sidebar still says where
	     you are. -->
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
			<!-- The month and the year used to be printed here as `AUGUST 2026`,
			     and both were already on screen twice over: the month in the spine
			     down the right edge and in the chapter rows, the year at the top of
			     the sidebar — and the first day heading in the column says the whole
			     date in the largest type on the page. This label was not even a
			     scroll indicator; it read off the lead day and never moved. The week
			     number stays because nothing else prints it. -->
			<!-- The album's own week, not the calendar's. `days` is newest first,
			     so the last of them is where this album starts. -->
			{#if lead && days.length}
				<span class="text-[12px] text-neutral-700">
					week {albumWeek(days[days.length - 1].key, lead.key)}
				</span>
			{/if}

			<!-- The album's name and everything you could do to it lived behind a
			     button here. Both card surfaces answer a hold with the same panel
			     now — see `FolderPanel` — so the name is in the sidebar where it
			     already was, and there is one less control on this screen. -->
		</div>
	</div>

	<div class="flex min-h-0 flex-1">
	<!-- ── Sidebar ─────────────────────────────────────────────────────────
	     No border. Cards on the tinted ground, which is the rule everywhere in
	     this design: a group is a white surface, never a rule. Collapsing it is
	     why the album's name repeats in the header. -->
	{#if !collapsed}
		<AlbumSidebar
			{shelf}
			{album}
			{folderId}
			{year}
			oncollapse={() => (collapsed = true)}
			onhold={(f, x, y) => (panel = { folder: f, x, y })}
		/>
	{/if}

			<div bind:this={column} class="flex min-w-0 flex-1 flex-col overflow-y-auto px-8 pb-16">
				{#if error}
					<p class="pb-4 text-[12px] text-accent-700">{error}</p>
				{/if}

				<!-- The overview sits above the days and, when opened, replaces them
				     rather than pushing them down — see `OverviewCard`. The unfiled
				     pile has no folder to describe, so it has no card. -->
				{#if album?.folder}
					{@const owner = album.folder}
					<div class="mb-[22px] flex min-h-0 shrink-0 flex-col" class:flex-1={overviewOpen}>
						<OverviewCard
							folder={owner}
							bind:expanded={overviewOpen}
							onsave={(text) => act(patchFolder(owner.id, { overview: text }))}
							onholdpicture={(x, y) => (heldPicture = { x, y })}
						/>
					</div>
				{/if}

				{#if overviewOpen}
					<!-- The days are gone while the overview is open. Nothing is
					     unmounted that costs anything to rebuild: `days` is derived. -->
				{:else}

				{#if loading && !album}
					<p class="text-[13px] text-neutral-700">reading…</p>
				{:else if days.length === 0}
					<p class="text-[13px] text-neutral-700">capture something and it will be here.</p>
				{:else if sheet}
					<!-- Words off. Everything ever made in here, densest possible —
					     the thing the ruler this replaced could never do. -->
					<div class="grid grid-cols-6 gap-1.5">
						{#each shots as shot, i (shot.entry.id + ':' + shot.ref)}
							<MediaTile
								ref={shot.ref}
								onopen={() => (lightbox = { shots, index: i })}
								onhold={(x, y) => (heldMedia = { ref: shot.ref, x, y })}
							/>
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
								onholdmedia={(ref, x, y) => (heldMedia = { ref, x, y })}
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
										onholdmedia={(ref, x, y) => (heldMedia = { ref, x, y })}
									/>
								{:else if expanded.has(row.days[0].key)}
									{#each row.days as day (day.key)}
										<LightDay
											{day}
											onopen={(s, index) => (lightbox = { shots: s, index })}
											ontoggle={onToggle}
											onassign={(entry, x, y) => (menu = { x, y, entry })}
										onholdmedia={(ref, x, y) => (heldMedia = { ref, x, y })}
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

{#if panel}
	{@const open = panel}
	<FolderPanel
		x={open.x}
		y={open.y}
		folder={open.folder}
		{unassigned}
		onpatch={(change) => {
			panel = null;
			act(patchFolder(open.folder.id, change));
		}}
		ondelete={() => remove(open.folder.id)}
		onclose={() => (panel = null)}
	/>
{/if}

{#if heldMedia && album?.folder}
	{@const held = heldMedia}
	{@const owner = album.folder}
	<HoldMenu x={held.x} y={held.y} width={250} onclose={() => (heldMedia = null)}>
		<button
			type="button"
			class="text-left text-[13px] font-semibold"
			onclick={() => {
				// The request first, the teardown second. Clearing `heldMedia`
				// destroys the block this handler is declared in, and its `@const`
				// bindings with it — reading `owner` afterwards is reading a scope
				// that is already gone, and the call quietly never happened.
				// Setting the picture on a folder with no overview creates one,
				// empty — the `!` on the card's bar is what says so afterwards.
				act(patchFolder(owner.id, { overview_media: held.ref }));
				heldMedia = null;
			}}
		>
			Set as overview profile
			<span class="mt-0.5 block text-[11px] font-normal text-neutral-700">
				the picture that stands for {owner.name}
			</span>
		</button>
	</HoldMenu>
{/if}

{#if heldPicture && album?.folder}
	{@const at = heldPicture}
	{@const owner = album.folder}
	<HoldMenu x={at.x} y={at.y} width={230} onclose={() => (heldPicture = null)}>
		<button
			type="button"
			class="text-left text-[13px] font-semibold text-accent-700"
			onclick={() => {
				// The request first: clearing `heldPicture` tears down the block
				// this handler is declared in, `@const` bindings and all.
				act(patchFolder(owner.id, { overview_media: '' }));
				heldPicture = null;
			}}
		>
			Remove picture
			<span class="mt-0.5 block text-[11px] font-normal text-neutral-700">
				the photograph stays in the log
			</span>
		</button>
	</HoldMenu>
{/if}
