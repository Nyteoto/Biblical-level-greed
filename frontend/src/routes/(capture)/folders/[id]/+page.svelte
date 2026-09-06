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
	import { goto, replaceState } from '$app/navigation';
	import FolderAssignMenu from '$lib/trophic/FolderAssignMenu.svelte';
	import LeadDay from '$lib/trophic/LeadDay.svelte';
	import AlbumFeed from '$lib/trophic/AlbumFeed.svelte';
	import Lightbox from '$lib/trophic/Lightbox.svelte';
	import MediaTile from '$lib/trophic/MediaTile.svelte';
	import AlbumSidebar from '$lib/trophic/AlbumSidebar.svelte';
	import MonthSpine from '$lib/trophic/MonthSpine.svelte';
	import Segmented from '$lib/trophic/Segmented.svelte';
	import TabPill from '$lib/trophic/TabPill.svelte';
	import Timer from '$lib/trophic/Timer.svelte';
	import { clockFace, duration, timer } from '$lib/trophic/timer.svelte';
	import { todayKey } from '$lib/trophic/day';
	import { albumWeek, groupDays } from '$lib/trophic/log';
	import { logSettings } from '$lib/trophic/settings.svelte';
	import { queuedTodo } from '$lib/trophic/queued.svelte';
	import { banner } from '$lib/trophic/banner-state.svelte';
	import type { Shot } from '$lib/trophic/media';
	import {
		assignEntry,
		deleteFolder,
		deleteGroup,
		getAlbum,
		getShelf,
		getUnassignedTags,
		logTime,
		nameChapter,
		orderGroups,
		patchFolder,
		renameGroup,
		toggleLine,
		type AlbumView,
		type Chapter,
		type Entry,
		type Folder,
		type Shelf,
		type UnassignedTag
	} from '$lib/trophic/api';
	import { lastAlbum } from '$lib/trophic/lastalbum.svelte';
	import FolderPanel from '$lib/trophic/FolderPanel.svelte';
	import OverviewCard from '$lib/trophic/OverviewCard.svelte';
	import Glyph from '$lib/trophic/Glyph.svelte';
	import HoldMenu from '$lib/trophic/HoldMenu.svelte';
	import ChapterPanel from '$lib/trophic/ChapterPanel.svelte';
	import GroupPanel from '$lib/trophic/GroupPanel.svelte';

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
	/** And the chapter's, from a hold on one of its rows. A chapter is a run of
	 *  months rather than a thing with an id, so what is held here is the whole
	 *  record — the panel needs its first month to anchor a name to. */
	let chapterPanel = $state<{ chapter: Chapter; x: number; y: number } | null>(null);
	/** And a group heading's, from a hold on one in the sidebar. The same panel
	 *  the year shelf opens: the heading is the same object on both screens, so
	 *  it answers a hold with the same thing on both. */
	let groupPanel = $state<{ name: string; x: number; y: number } | null>(null);
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

	let menu = $state<{ x: number; y: number; entry: Entry } | null>(null);
	let lightbox = $state<{ shots: Shot[]; index: number } | null>(null);
	let column = $state<HTMLElement | null>(null);

	const today = todayKey();
	const thisYear = String(new Date().getFullYear());

	/** `?entry=` — where the banner sends you. The row is put in the *middle* of
	 *  the column rather than at its top, because a reminder is read in context:
	 *  what you wrote around it is most of what it means, and a line pinned to
	 *  the top edge has half of that off-screen above it.
	 *
	 *  It runs when the entries arrive, not on mount — `days` is derived from a
	 *  fetch, so on mount there is nothing to scroll to. Once landed it clears
	 *  the parameter, so a later reload of the same URL does not yank you back
	 *  to a line you have since scrolled away from.
	 */
	const arrived = $derived(page.url.searchParams.get('entry'));
	/** A thread followed from inside this screen. Its own state rather than a
	 *  `replaceState` into `?entry=`: shallow routing does not re-run the
	 *  derived that reads the URL, so a tap on a reply set the address bar and
	 *  nothing else — the effect below never saw it. Arriving *at* the screen
	 *  still comes through the URL, which is what the banner uses and what
	 *  makes it survive a reload. */
	let target = $state('');
	const wanted = $derived(target || arrived);
	let landed = $state('');
	/** The line the reader was last sent to, marked until they look away. The
	 *  flash is over in under a second and is the wrong thing to rely on: a
	 *  jump that lands mid-column and leaves no trace makes you re-find by eye
	 *  the line the app had just found for you. See `.entry-held`. */
	let held = $state('');

	/** The day holding the line we were sent to. Handed to `AlbumFeed` as
	 *  `reveal`: if that day is inside a folded quiet stretch it opens it and
	 *  bumps `revealed`, which is a dependency of this effect, so the scroll
	 *  below happens on the next pass once the row is actually drawn. */
	const wantedDay = $derived(album?.entries.find((e) => e.id === wanted)?.day ?? '');
	let revealed = $state(0);

	$effect(() => {
		void revealed;
		if (!wanted || !column || days.length === 0 || landed === wanted) return;
		const row = column.querySelector<HTMLElement>(`[data-entry="${CSS.escape(wanted)}"]`);
		if (!row) return;
		landed = wanted;
		row.scrollIntoView({ block: 'center', behavior: 'smooth' });
		// A brief mark, so it is obvious which line you were sent to. It is a
		// class rather than a style so the animation lives with the rest of the
		// vocabulary in `trophic.css`.
		row.classList.add('entry-landed');
		setTimeout(() => row.classList.remove('entry-landed'), 900);
		held = wanted;
		target = '';
		if (arrived) {
			const url = new URL(page.url);
			url.searchParams.delete('entry');
			replaceState(url, {});
		}
	});

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

	/**
	 * The clock.
	 *
	 * The running session is device-local and lives in `timer.svelte.ts`; the
	 * total under the album's name is a derived read like every other figure on
	 * this screen. They meet in exactly one place — `stopAndLog` — and the
	 * ordering there is the same one the backend keeps: bank the number first,
	 * then send it, so a failed send leaves something to retry rather than a
	 * cleared clock.
	 */
	const clock = timer();
	let timerOpen = $state(false);
	/** A send that failed, kept where the folder's own screen can show it. The
	 *  seconds are still in hand: the timer was already banked, so this is a
	 *  number waiting to be re-sent rather than one that has been lost. */
	let unsent = $state<{ seconds: number; message: string } | null>(null);

	async function send(seconds: number) {
		// Zero is not worth a line in the log. Started and stopped by accident
		// is the commonest way to produce one, and a log full of `0s` sessions
		// makes the real ones harder to read.
		if (seconds <= 0) return;
		// The unfiled pile has no clock and no button, so this is unreachable
		// with a null id — but the type says otherwise and a silent send to
		// `/folders/null/time` is the wrong way to find that out.
		if (!folderId) return;
		try {
			await logTime(folderId, seconds);
			unsent = null;
			await refresh();
		} catch (e) {
			unsent = { seconds, message: e instanceof Error ? e.message : String(e) };
		}
	}

	async function stopAndLog() {
		const done = clock.stop();
		timerOpen = false;
		if (done) await send(done.seconds);
	}

	const days = $derived(groupDays(album?.entries ?? []));
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

	/** Follow a thread. It goes through the URL rather than straight to a
	 *  `scrollIntoView` so that both ways in — the banner's reminder and a tap
	 *  on a reply — land by exactly the same path, and so back works. */
	function jumpTo(entryId: string) {
		landed = '';
		target = entryId;
	}

	/** Let go of the mark. Any click that is not on the held line itself —
	 *  following a thread out of it sets a new one before this runs, which is
	 *  why it tests the id rather than clearing unconditionally. */
	function release(event: MouseEvent) {
		if (!held) return;
		const on = (event.target as HTMLElement | null)?.closest?.('[data-entry]');
		if (on instanceof HTMLElement && on.dataset.entry === held) return;
		held = '';
	}


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

	const queue = queuedTodo();

	async function onToggle(entry: Entry, line: number) {
		try {
			const { entry: updated } = await toggleLine(entry.id, line);
			if (album) album.entries = album.entries.map((e) => (e.id === updated.id ? updated : e));
			// Ticking here changes what the banner has to say — which todo is
			// oldest-open, and how much room is left under the cap.
			if (queue.is(entry.id, line)) queue.clear();
			banner().refresh();
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


<svelte:window onclick={release} onkeydown={(e) => e.key === 'Escape' && (held = '')} />

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

		<!-- Words off: everything ever made in here, densest possible. This is
		     the one view the deleted ruler could never give, and it lost its
		     button by accident when the properties moved into `FolderPanel` —
		     the view itself was never removed, only the way in.

		     Only when there is something to see, and not while the overview has
		     the column: the overview replaces the days, so a toggle that swapped
		     what is underneath it would appear to do nothing. -->
		<div class="flex items-center gap-3 text-[12px] text-neutral-700">
			<!-- ── The clock ────────────────────────────────────────────────
			     On the folder's own screen and nowhere else, because a session
			     is time spent on *this* project and there is no gesture that
			     would produce an unattributed one. The unfiled pile has no
			     button for the same reason — it is an album you can read, not a
			     project you can work on.

			     The button says the total when there is one, so the figure and
			     the way to add to it are the same object rather than a number
			     with a control next to it. -->
			{#if album?.folder}
				{@const clocked = album.folder.id}
				<!-- ── The one round control in the app ──────────────────────
				     Every other control on this screen is a rounded rectangle
				     with a word in it. This one is a circle with a mark in it,
				     and the difference is doing work: it is the only control
				     here that starts something that goes on running after you
				     look away, and it should not read as one more thing you
				     could tap. A circle in a row of pills is found without
				     being looked for.

				     The word moves into the label rather than disappearing —
				     the same rule `Glyph` follows — so the tooltip and the
				     screen reader both still say what it is and how much is on
				     it. -->
				<button
					type="button"
					aria-label={clock.isOn(clocked)
						? `timer, ${clock.running ? 'running' : 'paused'}`
						: 'timer'}
					title={clock.isOn(clocked)
						? `timer ${clock.running ? 'running' : 'paused'}`
						: `timer — ${duration(album.seconds)} clocked`}
					class="lift lift-sm flex h-[34px] w-[34px] shrink-0 items-center justify-center
					       rounded-full transition-colors {clock.isOn(clocked)
						? 'bg-ink text-ground'
						: 'bg-surface text-neutral-800 shadow-sm hover:text-ink'}"
					onclick={() => {
						// Opening the screen is what starts it, so the button is
						// one press rather than two. Already running on this
						// folder: just look at it.
						if (!clock.isOn(clocked)) clock.start(clocked, name);
						timerOpen = true;
					}}
				>
					<!-- `align="center"` because the mark is alone in a centred
					     box: the baseline nudge every inline use wants is a
					     1.4px drop here with nothing to align against. The
					     remaining pixel and a half is optical — the clock's
					     visible mass is its ring, and a ring reads low in a
					     ring. Both together are the ~3px this needed by eye. -->
					<span class="-translate-y-[1.5px]">
						<Glyph kind="time" size={16} align="center" />
					</span>
				</button>

				<!-- The running clock, beside the button rather than inside it,
				     so the button stays a circle. Only while a session is open
				     on this folder: the *total* is on the card, and printing it
				     here too would be the second place saying the same thing.

				     A pomodoro shows the stretch it is in, counting down, and
				     says which — the same thing the takeover shows, because a
				     glance at this row and a glance at that screen should never
				     have to be reconciled. -->
				{#if clock.isOn(clocked)}
					{@const pom = clock.pomodoro}
					<span
						class="tabular-nums {clock.running && pom?.phase !== 'rest'
							? 'text-ink'
							: 'text-neutral-600'}"
					>
						{pom ? clockFace(Math.ceil(pom.remainingMs / 1000)) : clockFace(clock.elapsedSeconds)}
						{#if pom}<span class="ml-1 text-[11px]">{pom.phase}</span>{/if}
					</span>
				{/if}
			{/if}

			<!-- A session that was measured and could not be sent. It is still
			     in hand — the timer banked it before the send — so this offers
			     the number back rather than reporting a loss. -->
			{#if unsent}
				<button
					type="button"
					class="rounded-lg px-[11px] py-1.5 text-error hover:underline"
					title={unsent.message}
					onclick={() => send(unsent!.seconds)}
				>
					{duration(unsent.seconds)} not logged — retry
				</button>
			{/if}

			{#if shots.length && !overviewOpen}
				<button
					type="button"
					aria-pressed={sheet}
					class="flex items-center gap-2 rounded-lg px-[11px] py-1.5 transition-colors {sheet
						? 'lift lift-sm bg-surface font-semibold text-ink shadow-sm'
						: 'hover:text-ink'}"
					onclick={() => (sheet = !sheet)}
				>
					<Glyph kind="media" count={shots.length} size={13} />
					<span class="tabular-nums">{shots.length}</span>
					<span>{sheet ? 'reading' : 'contact sheet'}</span>
				</button>
			{/if}
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
			onholdchapter={(chapter, x, y) => (chapterPanel = { chapter, x, y })}
			onholdgroup={(name, x, y) => (groupPanel = { name, x, y })}
			onorder={(order) => {
				// Applied here first for the same reason the year shelf does it:
				// the answer carries the whole shelf back, and headings that snap
				// to where they were for a round trip read as a drag that failed.
				if (!shelf?.year) return;
				shelf.groups = order;
				act(orderGroups(shelf.year, order));
			}}
		/>
	{/if}

			<div bind:this={column} class="flex min-w-0 flex-1 flex-col overflow-y-auto px-8 pb-16">
				{#if error}
					<p class="pb-4 text-[12px] text-accent-700">{error}</p>
				{/if}

				<!-- The overview sits above the days and, when opened, replaces them
				     rather than pushing them down — see `OverviewCard`. The unfiled
				     pile has no folder to describe, so it has no card.

				     And it is gone entirely under the contact sheet. Words off means
				     words off: the sheet is the one view that is only the pictures,
				     and a card of prose standing over it is the thing that view
				     exists to get out of the way. -->
				{#if album?.folder && !sheet}
					{@const owner = album.folder}
					<div class="mb-[22px] flex min-h-0 shrink-0 flex-col" class:flex-1={overviewOpen}>
						<OverviewCard
							folder={owner}
							bind:expanded={overviewOpen}
							onsave={(text) => act(patchFolder(owner.id, { overview: text }))}
							onholdpicture={(x, y) => (heldPicture = { x, y })}
							year={album.year}
							group={album.group}
							entries={album.entries.length}
							media={album.media_count}
							seconds={album.seconds}
							todos={album.todos}
							sentiments={album.sentiments}
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
								onjump={jumpTo}
								{held}
							/>
						{/if}

						<AlbumFeed
							days={days.slice(1)}
							onopen={(s, index) => (lightbox = { shots: s, index })}
							ontoggle={onToggle}
							onassign={(entry, x, y) => (menu = { x, y, entry })}
							onholdmedia={(ref, x, y) => (heldMedia = { ref, x, y })}
							onjump={jumpTo}
							{held}
							reveal={wantedDay}
							bind:revealed
						/>

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
		todos={target.todo_lines
			.filter((line) => !target.todo_done.includes(line))
			.map((line) => ({ line, text: target.clean_text.split('\n')[line]?.trim() ?? '' }))}
		queued={queue.key?.startsWith(`${target.id}:`)
			? Number(queue.key.split(':')[1])
			: null}
		onqueue={(line) => queue.set(target.id, line)}
	/>
{/if}

{#if chapterPanel}
	{@const held = chapterPanel}
	<ChapterPanel
		x={held.x}
		y={held.y}
		chapter={held.chapter}
		onrename={(to, at) => {
			chapterPanel = null;
			// The anchor arrives with the rename rather than being read off
			// `held` here, which by this line is a binding into a block that is
			// being torn down — see `ChapterPanel`.
			//
			// The album comes back from the write, so nothing here has to decide
			// what a rename did to the chapters around it: a name given to one
			// that has since merged with another changes which name the run
			// carries, and the server is where that is resolved.
			act(nameChapter(folderId, year, at, to));
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
		onrename={(to) => {
			// The request first, the teardown second — clearing `groupPanel`
			// destroys this block and every `@const` in it. The same note as the
			// media panels below, and the same bug if it is the other way round.
			act(renameGroup(on, held.name, to));
			groupPanel = null;
		}}
		ondelete={() => {
			act(deleteGroup(on, held.name));
			groupPanel = null;
		}}
		onclose={() => (groupPanel = null)}
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
			// The request first, the teardown second, for the reason written out
			// beside the media panels below: clearing `panel` destroys the block
			// this handler is declared in and every `@const` in it, so reading
			// `open` afterwards reads a scope that is already gone and the call
			// quietly never happens. It was the wrong way round here, which is
			// why renaming a folder from this sidebar did nothing at all.
			act(patchFolder(open.folder.id, change));
			panel = null;
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

<!-- ── The timer, taking the screen ────────────────────────────────────────
     Last in the file and outside every other block, so nothing on this page can
     clip it or tear it down mid-session. It is not `crt-exempt`: the glass
     covers it, because unlike a photograph it is the app talking. -->
{#if timerOpen}
	<Timer
		onstop={stopAndLog}
		onclose={() => (timerOpen = false)}
		ondiscard={() => {
			clock.discard();
			timerOpen = false;
		}}
	/>
{/if}
