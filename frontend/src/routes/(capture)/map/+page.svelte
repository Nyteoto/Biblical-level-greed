<script lang="ts">
	/**
	 * Map — what the year looked like.
	 *
	 * The year lens, and the reason the heatmap left the folder screen. It used
	 * to live one collapsed click inside every album's overview, where it
	 * answered a question nobody was asking at that moment; here it *is* the
	 * question, and asking it of one folder is the subject rather than a trip.
	 *
	 * ## Nothing on this screen is editable, and nothing on it chooses
	 *
	 * Creating a folder, renaming one, grouping, deleting — all of that is the
	 * shell's picker and Record's dossier. And **choosing** a folder is the
	 * shell's too: this screen carried the only folder list in the app for two
	 * steps, as a row of chips that was a filter and a door at once, which made
	 * picking one a journey to Map and then two presses. The grid draws whatever
	 * the subject bar says.
	 *
	 * ## Three things and their reads
	 *
	 *   - the totals — the shelf, read once for the whole app in
	 *     `subject.svelte.ts`, and cut to the folder when one is chosen;
	 *   - the **grid** — `/heat`, refetched when the subject changes. One trip
	 *     on loopback is imperceptible, and the alternative is a per-folder
	 *     per-day payload that exists only to avoid it;
	 *   - the **aside** — `/entries?date=`, for whichever day is pressed.
	 *
	 * The pressed day is in the URL like the scope is, so a Map you are looking
	 * at is a link.
	 */
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import YearGrid from '$lib/trophic/YearGrid.svelte';
	import ColorizedText from '$lib/trophic/ColorizedText.svelte';
	import Glyph from '$lib/trophic/Glyph.svelte';
	import ChapterBand from '$lib/trophic/ChapterBand.svelte';
	import { lensHref, readScope, thisYear } from '$lib/trophic/scope';
	import { lens } from '$lib/trophic/lens.svelte';
	import { subject } from '$lib/trophic/subject.svelte';
	import { duration } from '$lib/trophic/timer';
	import { clockLabel, dateLabel, monthAbbr, todayKey, weekdayLabel } from '$lib/trophic/day';
	import { quietTags } from '$lib/trophic/quiet';
	import { logSettings } from '$lib/trophic/settings.svelte';
	import { mediaViewUrl } from '$lib/trophic/api';
	import { plateFallback } from '$lib/trophic/media';
	import {
		getAlbum,
		getEntries,
		getHeat,
		search,
		type AlbumView,
		type Entry,
		type HeatDay,
		type SearchResult
	} from '$lib/trophic/api';

	const bar = subject();
	const scope = $derived(readScope(page.url));
	const day = $derived(page.url.searchParams.get('day') ?? '');
	const today = todayKey();

	/** The subject bar's, read once for the whole app. This screen used to
	 *  fetch its own — as did the Log and Record — which was three trips for
	 *  one fact and three copies of it to go stale. */
	const shelf = $derived(bar.data);
	let lines = $state<Entry[]>([]);

	/** The chosen folder's own row on the shelf, or null for everything and
	 *  for the unfiled pile — neither of which is a folder. */
	const chosen = $derived(
		scope.folder && scope.folder !== 'unfiled'
			? (shelf?.albums.find((a) => a.id === scope.folder) ?? null)
			: null
	);

	/**
	 * What the header counts. It printed the shelf's year totals whatever the
	 * subject bar said, so `phosphor` and every folder at once both read 430
	 * lines — a figure under a folder's grid that was not about the folder.
	 * The album row already carries the year's counts, cut the way the grid
	 * is. The unfiled pile has a line count on the shelf and no media count,
	 * so it says only what it knows.
	 */
	const totals = $derived.by(() => {
		if (!shelf) return null;
		if (!scope.folder) return { entries: shelf.entries, media: shelf.media as number | null };
		if (scope.folder === 'unfiled') return { entries: shelf.unfiled, media: null };
		return chosen ? { entries: chosen.entry_count, media: chosen.media_count as number | null } : null;
	});

	// The folder's own tags go quiet in the aside: it is the subject, and the
	// bar already says so. See `quiet.ts`.
	quietTags(() => chosen?.tags ?? []);

	$effect(() => {
		logSettings.hydrate();
	});

	/**
	 * The grid and the band, on one latch.
	 *
	 * They were two `$effect`s with byte-identical key strings — the same
	 * question asked twice, which is two chances for the copies to answer
	 * differently. One subject, one key, one load.
	 *
	 * Chapters belong to one folder, so they are only asked for when one is
	 * chosen. **They are authored** — cut by hand on Record, or from the page
	 * you are reading — so a folder nobody has cut draws no band at all, and
	 * this screen invents nothing to put there. A failure to read them is not
	 * a failure of the year: the grid is what this lens is for, so the album
	 * falls back to null and the heat's error is the one that surfaces.
	 */
	const view = lens(
		() => `${scope.year}:${scope.folder ?? ''}`,
		async () => {
			const [heat, chapters] = await Promise.all([
				getHeat(scope.year, scope.folder),
				scope.folder
					? getAlbum(scope.folder === 'unfiled' ? null : scope.folder, scope.year).catch(
							() => null
						)
					: Promise.resolve(null)
			]);
			return { days: heat.days, album: chapters };
		},
		{ days: [] as HeatDay[], album: null as AlbumView | null }
	);

	const days = $derived(view.data.days);
	const album = $derived(view.data.album);

	// The pressed day. Defaults to the newest day that has anything, so the
	// aside is never an empty panel asking to be filled.
	const pressed = $derived(day || days.at(-1)?.day || '');
	let lastDay = '';
	$effect(() => {
		// With a folder chosen the album answers this; see `mine` below.
		if (scope.folder || !pressed || pressed === lastDay) return;
		lastDay = pressed;
		getEntries({ date: pressed })
			.then((r) => (lines = r.entries))
			.catch(() => (lines = []));
	});

	/** The pressed day's lines, cut to the subject the way the grid is.
	 *
	 *  `/entries` reads by date alone, so a phosphor cell opened onto
	 *  everything written that day. With a folder chosen the album is already
	 *  in hand — it is what the chapter band is read from — and its entries are
	 *  the folder's, resolved by the server. Filtering `/entries` here instead
	 *  would mean resolving membership a second time in the browser, from the
	 *  tags, and missing every line filed by a directive or by hand. */
	const mine = $derived(
		scope.folder ? (album?.entries.filter((e) => e.day === pressed) ?? []) : lines
	);

	/** The month that counts as current, 1-based, and 0 in any year but this
	 *  one. Map used to light whichever chapter covered today's month number
	 *  whatever year was on screen, so a 2019 album lit its September. The
	 *  reading lens had this guard and Map did not, which is what two copies
	 *  of one band costs. */
	const liveMonth = $derived(scope.year === thisYear() ? Number(today.slice(5, 7)) : 0);

	const onDay = $derived(days.find((d) => d.day === pressed) ?? null);
	const media = $derived(mine.flatMap((e) => e.media.map((ref) => ({ ref, entry: e }))));
	const said = $derived(mine.filter((e) => e.clean_text.trim()));

	function press(key: string) {
		goto(lensHref('/map', scope, { day: key }), { noScroll: true, keepFocus: true });
	}

	// ── The jump field, carried over whole ──────────────────────────────────
	let jump = $state('');
	let jumpResults = $state<SearchResult[]>([]);
	let jumpOpen = $state(false);
	let jumpBox = $state<HTMLDivElement | null>(null);
	let jumpTimer: ReturnType<typeof setTimeout> | undefined;

	const resultHref = (entry: SearchResult) =>
		lensHref('/log', { folder: entry.home_folder ?? 'unfiled', year: entry.day.slice(0, 4) }, { entry: entry.id });

	function onJumpInput() {
		clearTimeout(jumpTimer);
		const query = jump.trim();
		if (!query || /^\d{4}-\d{2}-\d{2}$/.test(query)) {
			jumpResults = [];
			jumpOpen = false;
			return;
		}
		jumpTimer = setTimeout(async () => {
			try {
				const { entries } = await search({ q: query, limit: 6 });
				jumpResults = entries;
				jumpOpen = entries.length > 0;
			} catch {
				jumpResults = [];
				jumpOpen = false;
			}
		}, 220);
	}

	function outsideJump(event: Event) {
		if (jumpBox && !jumpBox.contains(event.target as Node)) jumpOpen = false;
	}

	function submitJump(event: SubmitEvent) {
		event.preventDefault();
		const query = jump.trim();
		if (!query) return;
		// **A date now lands on this screen** rather than leaving it. It used to
		// go to the unfiled album for that day, which was the only place a
		// single date could be shown; the grid is that place, so a date is a
		// cell to press.
		if (/^\d{4}-\d{2}-\d{2}$/.test(query)) {
			goto(lensHref('/map', { ...scope, year: query.slice(0, 4) }, { day: query }));
			jump = '';
			return;
		}
		const needle = query.toLowerCase().replace(/^[<\\]|>$/g, '');
		const hit = shelf?.albums.find(
			(a) => a.name.toLowerCase().includes(needle) || a.tags.some((t) => t.includes(needle))
		);
		if (hit) goto(lensHref('/log', { ...scope, folder: hit.id }));
		else if (jumpResults.length > 0) goto(resultHref(jumpResults[0]));
		else view.fail(new Error(`nothing here matches “${query}”`));
	}
</script>

<svelte:document onmousedown={outsideJump} />

<div class="flex min-h-0 flex-1">
	<!-- ═══ What the cursor is on ═══════════════════════════════════════════
	     The pressed day, in full. It is an aside rather than a popover because
	     the grid is for scanning and a panel that appears and disappears under
	     the pointer makes scanning impossible. -->
	<aside
		class="hidden w-[244px] shrink-0 flex-col gap-4 overflow-y-auto px-5 py-[22px] md:flex lg:w-[276px]"
		style="box-shadow:inset -1px 0 0 0 var(--color-neutral-400)"
	>
		{#if pressed}
			<div class="flex items-start gap-3">
				<div class="min-w-0">
					<div class="flex items-baseline gap-2.5">
						<span class="text-[52px] leading-[0.86] font-extrabold tracking-[-0.05em] tabular-nums">
							{Number(pressed.slice(8))}
						</span>
						<span class="text-[19px] font-bold text-neutral-700">
							{monthAbbr(pressed)}
						</span>
					</div>
					<div class="mt-2 text-[10px] font-bold tracking-[0.18em] text-neutral-600 uppercase">
						{weekdayLabel(pressed, true)}
					</div>
				</div>
				<!-- **It says what it does.** This was a bare `›` alone in the
				     panel's top-right corner, which is where a collapse control
				     lives in every app that has one — so it read as "fold this
				     panel away and give me the grid", and instead it navigated.
				     An `aria-label` is not a label: nothing sighted reads it.

				     It is drawn only when the scope names a folder, because
				     without one there is no album for a day to be opened *in*.
				     It used to be drawn anyway, and `/log?day=` with no folder
				     is a screen that cannot answer: the picker comes up over an
				     empty deck, or `Opens on: latest` bounces you to whichever
				     album was written in last. Neither is the day you pressed. -->
				{#if scope.folder && (said.length || media.length)}
					<a
						href={lensHref('/log', scope, { day: pressed })}
						class="-mt-1 -mr-1 ml-auto flex shrink-0 items-center gap-1 self-start py-1 text-[10px] font-bold tracking-[0.12em] text-neutral-700 uppercase transition-colors hover:text-ink"
					>
						read
						<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m9 5 7 7-7 7" /></svg>
					</a>
				{/if}
			</div>

			<div class="flex items-center gap-4 text-[12px] text-neutral-700 tabular-nums">
				<span class="flex items-center gap-1.5">
					<Glyph kind="entries" count={mine.length} size={13} />{mine.length}
				</span>
				{#if media.length}
					<span class="flex items-center gap-1.5">
						<Glyph kind="media" count={media.length} size={13} />{media.length}
					</span>
				{/if}
				{#if onDay?.seconds}
					<span class="flex items-center gap-1.5">
						<Glyph kind="time" size={13} />{duration(onDay.seconds)}
					</span>
				{/if}
				{#if onDay?.points}
					<span class="ml-auto text-[15px] font-extrabold text-ink">+{onDay.points}</span>
				{/if}
			</div>

			{#if media.length}
				<div class="flex flex-col gap-1">
					<button
						type="button"
						aria-label="open the photograph"
						class="h-[128px] w-full overflow-hidden bg-neutral-300"
						style="box-shadow:inset 0 0 0 1px var(--color-neutral-500)"
					>
						<img
							src={mediaViewUrl(media[0].ref)}
							alt=""
							onerror={(e) => plateFallback(e, media[0].ref)}
							class="h-full w-full object-cover"
						/>
					</button>
					{#if media.length > 1}
						<div class="flex gap-1">
							{#each media.slice(1, 3) as shot (shot.entry.id + ':' + shot.ref)}
								<span class="h-[74px] flex-1 overflow-hidden bg-neutral-300">
									<img
										src={mediaViewUrl(shot.ref)}
										alt=""
										loading="lazy"
										onerror={(e) => plateFallback(e, shot.ref)}
										class="h-full w-full object-cover"
									/>
								</span>
							{/each}
						</div>
					{/if}
				</div>
			{/if}

			<div class="flex flex-col gap-3.5">
				{#each said.slice(0, 5) as entry (entry.id)}
					<div class="flex gap-3">
						<span class="w-[34px] shrink-0 text-[11px] text-neutral-600 tabular-nums">
							{clockLabel(entry.ts)}
						</span>
						<p class="m-0 min-w-0 text-[14px] leading-[1.5] font-light">
							<ColorizedText text={entry.clean_text} />
						</p>
					</div>
				{:else}
					<p class="text-[13px] text-neutral-600">Nothing was written this day.</p>
				{/each}
			</div>
		{:else}
			<p class="text-[13px] text-neutral-600">Press a day.</p>
		{/if}
	</aside>

	<!-- ═══ The field ═══════════════════════════════════════════════════════ -->
	<main class="flex min-h-0 min-w-0 flex-1 flex-col px-7 py-[22px]">
		<div class="flex shrink-0 flex-wrap items-baseline gap-x-5 gap-y-3">
			<h1 class="text-[42px] leading-none font-extrabold tracking-[-0.04em] tabular-nums">
				{scope.year === 'all' ? 'All' : scope.year}
			</h1>
			{#if totals}
				<span class="flex items-center gap-3.5 text-[12px] text-neutral-700 tabular-nums">
					<span class="flex items-center gap-1.5">
						<Glyph kind="entries" count={totals.entries} size={13} />{totals.entries.toLocaleString()}
					</span>
					{#if totals.media !== null}
						<span class="flex items-center gap-1.5">
							<Glyph kind="media" count={totals.media} size={13} />{totals.media.toLocaleString()}
						</span>
					{/if}
				</span>
			{/if}

			<!-- The year switcher stood here and is in the shell's subject bar
			     now, with the folder. Both are the *subject*, and a subject that
			     can only be changed from one lens is why you had to come to Map
			     to choose a folder before you could read one. -->
			<div class="ml-auto flex items-center gap-2">
				<div class="relative min-w-0 sm:min-w-[230px]" bind:this={jumpBox}>
					<form
						class="focus-pill flex min-w-0 items-center gap-2.5 bg-surface px-3.5 py-[11px]"
						onsubmit={submitJump}
					>
						<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" class="shrink-0 text-neutral-600" aria-hidden="true"><circle cx="11" cy="11" r="7" /><path d="m20 20-3.6-3.6" /></svg>
						<input
							bind:value={jump}
							oninput={onJumpInput}
							onfocus={() => (jumpOpen = jumpResults.length > 0)}
							placeholder="Find a date, tag or word"
							class="min-w-0 flex-1 bg-transparent text-[13px] placeholder:text-neutral-600"
						/>
					</form>
					{#if jumpOpen && jumpResults.length > 0}
						<div
							class="absolute top-[calc(100%+6px)] right-0 left-0 z-30 flex max-h-[320px] flex-col gap-0.5 overflow-y-auto bg-surface p-1.5 shadow-lg"
						>
							{#each jumpResults as result (result.id)}
								<a
									href={resultHref(result)}
									class="flex flex-col gap-0.5 px-2.5 py-1.5 transition-colors hover:bg-neutral-200"
									onclick={() => (jumpOpen = false)}
								>
									<span class="truncate text-[13px] leading-snug font-light">
										<ColorizedText text={result.clean_text.slice(0, 140)} />
									</span>
									<span class="text-[11px] text-neutral-600">{dateLabel(result.day)}</span>
								</a>
							{/each}
						</div>
					{/if}
				</div>
			</div>
		</div>

		<!-- The chip row of folders stood here. It was the only place in the app
		     a folder could be chosen, which made choosing one a trip to Map —
		     and it was a filter and a door at the same time, so it needed two
		     presses to mean the second. It is the shell's subject bar now, and
		     this grid simply draws whatever the bar says. -->

		{#if view.error}
			<p class="mt-3 shrink-0 text-[12px] text-error">{view.error}</p>
		{/if}

		{#if scope.year === 'all'}
			<!-- Twelve columns of every year at once is not a shape. The setting
			     stays honoured; the grid simply has nothing to draw. -->
			<p class="mt-10 text-[13px] text-neutral-600">Pick a year.</p>
		{:else}
			<!-- Chapters, as spans over the months they cover. One folder only:
			     a chapter belongs to *one* album, so with everything selected
			     there is no single answer to draw.

			     **Oldest first here, and only here.** Every other list in this
			     app reads newest first, and so does `chapters` — but a grid
			     places items in source order, and an item whose column sits
			     *behind* the cursor is pushed to a new row. Newest first, three
			     chapters therefore drew as three stacked bands and took the
			     bottom of the year off the screen. This band is spatial rather
			     than a list: its order is the calendar's. -->
			{#if scope.folder && album && album.chapters.length}
				<div class="mt-3 flex shrink-0 gap-2.5">
					<span class="w-[26px] shrink-0"></span>
					<div class="min-w-0 flex-1">
						<ChapterBand chapters={album.chapters} current={liveMonth} />
					</div>
				</div>
			{/if}

			<!-- Tight on purpose: 31 rows plus the heads want ~575px, and an iPad
				     in landscape with a two-line strip above it has about that. Every
				     margin here is buying the 31st of the month a place on the screen.
				     It scrolls when it still does not fit, which is the graceful end of
				     that and not the intent. -->
				<div class="mt-2 min-h-0 flex-1 overflow-y-auto pb-2">
				<YearGrid
					year={scope.year}
					{days}
					{today}
					selected={pressed}
					onpick={press}
				/>
				{#if view.loading}
					<p class="mt-4 text-[12px] text-neutral-600">Reading…</p>
				{/if}
			</div>
		{/if}
	</main>
</div>
