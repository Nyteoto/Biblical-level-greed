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
	 * **Reaching history must not cost travel.** The index's month rows and its
	 * chapters are constant-cost, and the year cap is what keeps them
	 * constant-*size*: twelve rows, whatever the project's age. If something
	 * here starts needing a scroll — or a run of page turns — to *reach* rather
	 * than to *read*, it has gone backwards.
	 *
	 * The header is the band and two buttons, and nothing else. It carried a
	 * week number, a pill naming the cut, a `chapter starts here` in prose, a
	 * round timer and a worded contact-sheet toggle — four kinds of thing in
	 * one row. The cut is the lit column on the band and pressing it again
	 * hands the year back; a chapter is started from a mark on the band at the
	 * month being read; the two buttons are the same square.
	 *
	 * ## A day is a page
	 *
	 * Below the header this is a deck, not a feed: one day on screen at a time,
	 * turned by the edges either side of it. See `PageDeck` for why that is not
	 * a step backwards from the scroll it replaced, and `paginate` in `log.ts`
	 * for what goes on a page — including the continuation pages a heavy day
	 * gets, which is the only place a day is ever split.
	 *
	 * Every page gets the whole treatment now. The old split — the newest day
	 * dressed with its photograph, three hundred others reduced to a grey line
	 * — was a rationing of one shared scroll, and there is no shared scroll to
	 * ration any more.
	 *
	 * ## A month is a filter, not a floor
	 *
	 * There used to be a screen below this one at `[month]/+page.svelte`, with
	 * its own copy of the sidebar, the spine, the panels and the feed. It is
	 * gone: a month is this album with fewer days in it, so it is `?month=` on
	 * this route, and a chapter is `?chapter=`. One view, one set of rules, and
	 * nothing left for two copies of them to drift apart over — which they had.
	 */
	import { page } from '$app/state';
	import { goto, replaceState } from '$app/navigation';
	import FolderAssignMenu from '$lib/trophic/FolderAssignMenu.svelte';
	import PageDeck from '$lib/trophic/PageDeck.svelte';
	import Lightbox from '$lib/trophic/Lightbox.svelte';
	import MediaTile from '$lib/trophic/MediaTile.svelte';
	import MonthBand from '$lib/trophic/MonthBand.svelte';
	import Segmented from '$lib/trophic/Segmented.svelte';
	import Timer from '$lib/trophic/Timer.svelte';
	import { clockFace, duration, timer } from '$lib/trophic/timer.svelte.js';
	import { todayKey } from '$lib/trophic/day';
	import {
		groupDays,
		inScope,
		monthLabel,
		pageAt,
		pageOfEntry,
		paginate,
		WHOLE_YEAR
	} from '$lib/trophic/log';
	import type { DeckScope } from '$lib/trophic/log';
	import { readScope, lensHref } from '$lib/trophic/scope';
	import { lens } from '$lib/trophic/lens.svelte';
	import { logSettings } from '$lib/trophic/settings.svelte';
	import { queuedTodo } from '$lib/trophic/queued.svelte';
	import { banner } from '$lib/trophic/banner-state.svelte';
	import type { Shot } from '$lib/trophic/media';
	import {
		assignEntry,
		getAlbum,
		logTime,
		splitChapter,
		unsplitChapter,
		patchFolder,
		toggleLine,
		type AlbumView,
		type Chapter,
		type Entry
	} from '$lib/trophic/api';
	import { subject } from '$lib/trophic/subject.svelte';
	import Glyph from '$lib/trophic/Glyph.svelte';
	import HoldMenu from '$lib/trophic/HoldMenu.svelte';
	import ChapterPanel from '$lib/trophic/ChapterPanel.svelte';
	import { quietTags } from '$lib/trophic/quiet';

	/**
	 * The subject, read off the scope rather than off a route parameter.
	 *
	 * This screen used to be `/folders/[id]`, which made the folder part of
	 * *where you were*. It is not: it is what every lens in the rail is a
	 * question about, so it lives in the query and survives switching between
	 * them. See `scope.ts`.
	 *
	 * With no folder named there is nothing to read, and the subject bar's
	 * picker is where one is chosen — see the effect below, which opens it
	 * rather than sending you somewhere else to answer.
	 */
	const bar = subject();
	const scope = $derived(readScope(page.url));
	const id = $derived(scope.folder ?? '');
	/** `unfiled` is an album you can open like any other and is not a folder. */
	const folderId = $derived(id === 'unfiled' ? null : id);
	const year = $derived(scope.year);

	/**
	 * **No folder chosen is not a redirect any more.**
	 *
	 * There is no "all folders" album — the server has no such read — so this
	 * lens genuinely needs one. It used to answer that by bouncing you to Map,
	 * which was the app deciding you had meant to go somewhere else. The
	 * subject bar is where a folder is chosen now, so the honest answer is to
	 * open it: the one press you need is already down, and the empty deck says
	 * what is missing.
	 *
	 * `Opens on: latest` is the exception, and it is not the app deciding: it
	 * is the reader having answered this question in advance. It used to be a
	 * `load` on **Map**, which redirected the year away to an album — so with
	 * the setting on, pressing Map in the rail never showed you the year at
	 * all. The escape hatch for that was `?shelf`, and nothing set it once the
	 * rail owned the lenses, which made the year a place you could not get to.
	 * The setting's own label says "what the Log opens on", and this is the
	 * Log.
	 */
	$effect(() => {
		if (scope.folder) return;
		if (logSettings.openOn !== 'latest') {
			bar.open();
			return;
		}
		// Wait for the shelf rather than opening the picker in the meantime:
		// a picker that appears and is then navigated out from under you is
		// worse than the half-second of an empty deck.
		const shelf = bar.data;
		if (!shelf) return;
		const target = shelf.latest
			? (shelf.latest.folder ?? 'unfiled')
			: (shelf.albums[0]?.id ?? (shelf.unfiled > 0 ? 'unfiled' : null));
		// A year with nothing in it at all has no latest album to open, so the
		// question falls back to being asked.
		if (!target) {
			bar.open();
			return;
		}
		// Carry what was asked for. A link that names a day, a month, a chapter
		// or an entry is asking for *that*, and answering it by opening the
		// latest album at its newest page throws the question away — which is
		// what this did: `/log?day=…` with no folder landed you on whichever
		// album was written in last, at the wrong day, with nothing to say so.
		const asked: Record<string, string> = {};
		for (const key of ['day', 'month', 'chapter', 'entry']) {
			const value = page.url.searchParams.get(key);
			if (value) asked[key] = value;
		}
		goto(lensHref('/log', { folder: target, year: shelf.year ?? year }, asked), {
			replaceState: true
		});
	});

	/**
	 * The scope: which pages are in the deck.
	 *
	 * **This is the whole of what used to be a second screen.** A month was its
	 * own route — `/folders/[id]/[month]` — with its own copy of the sidebar,
	 * the spine, the panels and the feed, and the two had already drifted: the
	 * month passed no `onassign` and no `onholdmedia`, so holding an entry
	 * worked on one screen and drew the null ring on the next. A month is not
	 * another place; it is this album with fewer days in it. So it is a filter
	 * on one view, and so is a chapter.
	 *
	 * Both are read off the URL rather than held in state, so a scoped album is
	 * a link you can send yourself, land on from the shelf, and reload into.
	 */
	const monthParam = $derived(page.url.searchParams.get('month')); // `YYYY-MM`
	/** The cut a chapter begins at, which is that chapter's identity. */
	const chapterParam = $derived(page.url.searchParams.get('chapter')); // `YYYY-MM`

	/** The shelf is the subject bar's, read once for the whole app. This lens
	 *  wants two small things from it — the year below, and the folders the
	 *  assign menu can file a line into — and used to fetch its own copy, which
	 *  is how a folder renamed elsewhere kept its old name in that menu. */
	const shelf = $derived(bar.data);

	/** Whether the contact sheet is showing instead of the deck.
	 *  Named `contacts` and not `sheet`: in this file a *sheet* is the fixed
	 *  surface `PageDeck` owns and every page prints on, which is a different
	 *  thing that the word was already taken by. */
	let contacts = $state(false);

	/**
	 * There is no sidebar to fold any more.
	 *
	 * The index — the months and the chapters — lies down in the header row as
	 * `MonthBand`, and the folder list went to the shell's subject bar. What
	 * this replaces was 218px of column that hid itself below 1024px and
	 * latched the reader's choice, which was most of why the furniture felt
	 * unpredictable: four lenses, four different columns, three different
	 * widths at which they vanished. There is nothing left here to collapse.
	 */

	/** A chapter held in the index. The whole record is carried rather than the
	 *  cut alone, because the panel prints what it is about to rename or
	 *  un-cut — the span and the line count — and reading that back off the
	 *  album afterwards is reading a list the write is about to replace.
	 *
	 *  It is the only panel left on this screen. Holding a *folder* opened its
	 *  properties here until the rail arrived; everything you can do to a
	 *  folder is Record's now, and a reading lens that could also rename and
	 *  delete the thing it was reading was the shelf's old mistake in a new
	 *  place. */
	let chapterPanel = $state<{ chapter: Chapter; x: number; y: number } | null>(null);
	/** A held photograph, and what can be done with it. One option — make it
	 *  the folder's face — and it stays on *this* lens even though the overview
	 *  it feeds now lives on Record, because this is the only lens with
	 *  photographs in it to choose from. */
	let heldMedia = $state<{ ref: string; x: number; y: number } | null>(null);

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

	$effect(() => {
		// The page the deck is on is a dependency, not decoration: landing on a
		// line is two steps — the effect above turns the deck to the page
		// holding it, and only then is there a row in the DOM to find. Without
		// this read the second step never runs, because nothing else in here
		// changes when the page does. It is the same reason the feed version of
		// this used to read `revealed`.
		void openPage;
		if (!wanted || !column || pages.length === 0 || landed === wanted) return;
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

	/** The album. `id` and not `folderId` in the key, because `unfiled` is an
	 *  album you can be reading like any other — it is just not a folder. */
	const view = lens(
		() => `${id}:${year}`,
		async () => (scope.folder ? await getAlbum(folderId, year) : null),
		null as AlbumView | null
	);

	const album = $derived(view.data);

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
	 *  number waiting to be re-sent rather than one that has been lost.
	 *
	 *  `tries` is what makes a retry visible. A second attempt against the same
	 *  broken thing fails with the same message, so without a count the screen
	 *  is byte-identical before and after the press and the button reads as
	 *  dead — which is exactly how this was first reported. */
	let unsent = $state<{ seconds: number; message: string; tries: number } | null>(null);
	let sending = $state(false);

	async function send(seconds: number) {
		// Zero is not worth a line in the log. Started and stopped by accident
		// is the commonest way to produce one, and a log full of `0s` sessions
		// makes the real ones harder to read.
		if (seconds <= 0) return;
		// The unfiled pile has no clock and no button, so this is unreachable
		// with a null id — but the type says otherwise and a silent send to
		// `/folders/null/time` is the wrong way to find that out.
		if (!folderId) return;
		sending = true;
		const attempt = (unsent?.tries ?? 0) + 1;
		try {
			await logTime(folderId, seconds);
			unsent = null;
			await view.refresh();
		} catch (e) {
			const raw = e instanceof Error ? e.message : String(e);
			unsent = { seconds, message: explain(raw), tries: attempt };
		}
		sending = false;
	}

	/** Turn a wire failure into something that says what to do about it.
	 *
	 *  `Not Found` is what a server without the route answers, and on its own
	 *  it is the least useful sentence in the app — it reads as "your session
	 *  is gone" when the session is fine and the *server* is old. The shell
	 *  already has the machinery for that case and offers a restart; this only
	 *  has to stop the screen contradicting it. */
	function explain(raw: string): string {
		if (/not found/i.test(raw)) return 'this server is too old to record time — restart it';
		if (/offline|failed to fetch|networkerror/i.test(raw)) return 'no connection';
		return raw;
	}

	async function stopAndLog() {
		const done = clock.stop();
		timerOpen = false;
		if (done) await send(done.seconds);
	}

	const days = $derived(groupDays(album?.entries ?? []));

	/** The chapter the scope names, if it names one. `?chapter=` is the cut
	 *  itself, which is the chapter's identity, so this is an exact match — it
	 *  used to search by first month, because a derived run had no id and its
	 *  far end could move when two of them merged. Neither is true of a cut. */
	const chapter = $derived(
		chapterParam && album ? (album.chapters.find((c) => c.month === chapterParam) ?? null) : null
	);

	/** How the album is cut. A value rather than two branches, so `paginate`
	 *  and the contact sheet are handed the same question — the filter itself
	 *  lives in `log.ts` beside the page budget, where `verify:ui` can see it.
	 */
	const deckScope = $derived<DeckScope>(
		monthParam
			? { kind: 'month', month: monthParam }
			: chapter
				? {
						kind: 'chapter',
						first_month: chapter.first_month,
						last_month: chapter.last_month
					}
				: WHOLE_YEAR
	);

	/** What the scope is called, for the pill that says one is on. */
	const scopeName = $derived(
		monthParam ? monthLabel(monthParam).split(' ')[0] : chapter ? chapter.name : ''
	);

	const pages = $derived(paginate(days, deckScope));
	/** Every attachment in scope, newest first — the contact sheet. Through
	 *  the same filter the deck is cut by, never a second reading of it. */
	const shots = $derived(inScope(days, deckScope).flatMap((d) => d.media));

	/**
	 * Which page is open.
	 *
	 * Plain state rather than a URL parameter: turning a page is reading, and a
	 * history entry per day read would bury the back button. What the URL *does*
	 * decide is where you land — `?day=` and `?entry=` — and the effect below is
	 * the one place that is honoured.
	 */
	let deckIndex = $state(0);
	/** The deck-and-request this last acted on. One latch rather than two
	 *  effects, because a new deck and a new request arrive together often
	 *  enough — a reminder in another year opens a different album *and* asks
	 *  for a line in it — and two effects racing to set one index is how the
	 *  wrong page wins. */
	let honoured = $state('');
	const askedDay = $derived(page.url.searchParams.get('day'));

	/** The page actually on screen. Clamped the same way `PageDeck` clamps, so
	 *  the header and the deck cannot disagree about which day is being read
	 *  while a shorter deck is arriving. */
	const openPage = $derived(
		pages[Math.min(Math.max(deckIndex, 0), Math.max(pages.length - 1, 0))] ?? null
	);

	$effect(() => {
		const ask = wanted ? `e:${wanted}` : askedDay ? `d:${askedDay}` : '';
		const stamp = `${id}:${year}:${monthParam ?? ''}:${chapterParam ?? ''}|${ask}`;
		if (stamp === honoured) return;
		// A request has to wait for the fetch; an empty deck with nothing asked
		// of it is simply an empty album.
		if (ask && pages.length === 0) return;
		honoured = stamp;
		const at = wanted
			? pageOfEntry(pages, wanted)
			: askedDay
				? pageAt(pages, askedDay)
				: 0;
		deckIndex = at >= 0 ? at : 0;
	});

	// Inside a folder's album its own tags say nothing — see `quiet.ts`.
	quietTags(() => album?.folder?.tags ?? []);

	/** Whether the page on screen is already inside a cut of its own month —
	 *  which is the one case where the band's cut mark would do nothing. */
	const cutHere = $derived(
		!!openPage && !!album?.chapters.some((c) => c.month === openPage.day.key.slice(0, 7))
	);

	const liveMonth = $derived(year === thisYear || year === 'all' ? new Date().getMonth() : -1);
	const previousYear = $derived(shelf?.previous?.year ?? null);

	const name = $derived(album?.folder?.name ?? 'Unfiled');
	/**
	 * Narrow the deck, or hand it back the whole year.
	 *
	 * A scope change clears `?day=` and `?entry=` with it: they name a page in
	 * the deck that is being replaced, and honouring a landing request against
	 * a deck it was not made for is how you end up on a page nobody asked for.
	 * It pushes rather than replaces, so the back button returns you to the
	 * whole year — which is the one thing a filter has to be undoable by.
	 */
	function scopeTo(next: { month?: string; chapter?: string }) {
		const url = new URL(page.url);
		for (const key of ['month', 'chapter', 'day', 'entry']) url.searchParams.delete(key);
		if (next.month) url.searchParams.set('month', next.month);
		if (next.chapter) url.searchParams.set('chapter', next.chapter);
		goto(url, { noScroll: true, keepFocus: true });
	}

	/** The index picks a month, and a month is a scope rather than a screen.
	 *  Nothing scrolls afterwards: a new scope is a new deck, and a new deck
	 *  opens at its first page — which is a fresh sheet already at its top. */
	function jumpToMonth(month: number) {
		const key = `${year}-${String(month + 1).padStart(2, '0')}`;
		// The lit column is the cut, so pressing it again is the way back out —
		// which is what the pill that named the cut used to be for.
		scopeTo(monthParam === key ? {} : { month: key });
	}

	function jumpToChapter(chapter: Chapter) {
		scopeTo(chapterParam === chapter.month ? {} : { chapter: chapter.month });
	}

	/** Follow a thread. It goes through the URL rather than straight to a
	 *  `scrollIntoView` so that both ways in — the banner's reminder and a tap
	 *  on a reply — land by exactly the same path, and so back works. */
	function jumpTo(entryId: string) {
		landed = '';
		// **A thread almost always crosses a filter.** You answer a prompt now
		// and the line it answers is months back, so following one while the
		// deck is cut to August would land on nothing at all. Hand the whole
		// year back first; the deck it needs is the one the reader started
		// from. Scoped or not, `target` survives the navigation — it is state
		// on a component the route does not remount.
		const standing = pages.some((page) => page.day.entries.some((e) => e.id === entryId));
		if (!standing && (monthParam || chapterParam)) scopeTo({});
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
		view.clear();
		try {
			await work;
		} catch (e) {
			view.fail(e);
		}
		await view.refresh();
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
			view.fail(e);
		}
	}

</script>


<svelte:window onclick={release} onkeydown={(e) => e.key === 'Escape' && (held = '')} />

<!-- `min-h-0 flex-1`, not `h-dvh`: the shell owns the viewport now and this
     is the remainder under the rail and the strip. It was a full viewport
     *below* the banner, which made the document taller than the window by the
     height of the strip on every screen in the app. -->
<div class="flex min-h-0 flex-1 flex-col">
	<!-- ── Header ────────────────────────────────────────────────────────
	     One row across the whole page, above the sidebar rather than beside
	     it, so the nav pill is in the same corner here as on every other
	     screen. It used to sit at the top of the sidebar, which put it in a
	     third place — and a navigation control that moves is one you have to
	     look for every time.

	     The band on the left, two square buttons on the right. The folder's
	     name is the subject bar's, above this row. -->
	<div
		class="flex shrink-0 flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 pt-[22px] pb-[22px] sm:px-[34px]"
	>
		<div class="flex min-w-0 flex-1 items-center gap-3.5">
			<!-- ── The index, lying down ──────────────────────────────────
			     Twelve months and the chapters over them, in the header row
			     rather than in a column beside the deck — see `MonthBand`.
			     One row of chrome where there were two and a sidebar. -->
			{#if album}
				<div class="hidden min-w-0 max-w-[560px] flex-1 sm:flex">
					<MonthBand
						{album}
						live={liveMonth}
						month={monthParam ?? chapterParam}
						reading={openPage ? openPage.day.key.slice(0, 7) : null}
						oncut={openPage && !cutHere
							? () => act(splitChapter(folderId, openPage.day.key.slice(0, 7), ''))
							: undefined}
						onpickmonth={jumpToMonth}
						onpickchapter={jumpToChapter}
						onholdchapter={(chapter, x, y) => (chapterPanel = { chapter, x, y })}
					/>
				</div>
			{/if}
			<!-- The week number stood here, then a pill naming the cut, then
			     `chapter starts here` in prose. The week said where the page was
			     in the album, which the band's lit column already says; the pill
			     said what the deck was cut to, which the band's lit column also
			     says; and the chapter control is a mark on the band now, at the
			     month being read — the place a cut is drawn is the place it is
			     made. -->
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
				<!-- ── Two square buttons, a mark in each ─────────────────────
				     This was the one round control in the app, set apart on
				     purpose because it starts something that keeps running.
				     A running clock says so on its own — it fills, and its
				     time is printed beside it — so the circle was a second
				     way of saying that, and a fourth shape in one row. It is
				     the contact sheet's twin now.

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
					       transition-colors {clock.isOn(clocked)
						? 'accent-fill'
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
				<!-- The reason is on the screen, not in a `title`. This app is
				     read on an iPad, where there is no hover and a tooltip is a
				     thing that does not exist — a failure whose explanation
				     lives in one is a failure with no explanation. -->
				<span class="flex items-center gap-2 text-error">
					<span>{duration(unsent.seconds)} not logged — {unsent.message}</span>
					<button
						type="button"
						class=" px-2 py-1 font-semibold underline disabled:no-underline
						       disabled:opacity-60"
						disabled={sending}
						onclick={() => send(unsent!.seconds)}
					>
						{sending ? 'sending…' : 'retry'}
					</button>
					{#if unsent.tries > 1}
						<span class="tabular-nums opacity-80">{unsent.tries} tries</span>
					{/if}
				</span>
			{/if}

			{#if shots.length}
				<button
					type="button"
					aria-pressed={contacts}
					aria-label="contact sheet, {shots.length} {shots.length === 1 ? 'photograph' : 'photographs'}"
					title="contact sheet · {shots.length}"
					class="lift lift-sm flex h-[34px] w-[34px] shrink-0 items-center justify-center transition-colors {contacts
						? 'accent-fill'
						: 'bg-surface text-neutral-800 shadow-sm hover:text-ink'}"
					onclick={() => (contacts = !contacts)}
				>
					<Glyph kind="media" count={shots.length} size={16} align="center" />
				</button>
			{/if}
		</div>
	</div>

	<div class="flex min-h-0 flex-1">
	<!-- No column on either side of the deck. The folder list is the shell's
	     subject bar and the months and chapters are the band in the header —
	     which is the "index collapsed" page, as the only page. -->
			<!-- **The furniture holds still and the page turns underneath it.**
			     `overflow-hidden` rather than a scroll on the whole column: the
			     deck below wants a bounded height so that a long page scrolls
			     *inside itself*, which is what keeps the edges that turn it on
			     screen. A column that scrolled as a whole would carry them off
			     the bottom, and turning a page would mean scrolling back up to
			     find the way to do it. -->
			<div bind:this={column} class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden px-3 sm:px-8">
				{#if view.error}
					<p class="shrink-0 pb-4 text-[12px] text-accent-700">{view.error}</p>
				{/if}

				<!-- The readings that used to stand here are gone, and the rail is
				     why. A year of days is Map's whole question now, and drawing it
				     again above the reading view was the same fact in two places —
				     the duplication the lenses exist to end. The pattern counts
				     went with them, to Record, where the folder is described in
				     figures. -->

				<!-- The overview card stood here and is on Record now. It was the
				     folder's standing description, its face and a row of figures —
				     the one thing on the reading lens that was never a fold over
				     captures, and the same figures Record prints. What is left is
				     the reading, which is what this lens is for: the screen opens
				     straight onto the stack. -->

				{#if view.loading && !album}
					<p class="text-[13px] text-neutral-700">reading…</p>
				{:else if pages.length === 0}
					<p class="text-[13px] text-neutral-700">
						{scopeName
							? `nothing was written in ${scopeName}.`
							: 'capture something and it will be here.'}
					</p>
				{:else if contacts}
					<!-- Words off. Everything made in what is in scope, densest
					     possible — the thing the ruler this replaced could never do.
					     It reads `shots`, which the filter has already cut, so a
					     month in scope gives the month's contact sheet. That is the
					     whole of what the month screen's photo strip used to be.

					     Its own scroll, because the column around it no longer has
					     one to lend. -->
					<div class="min-h-0 flex-1 overflow-y-auto pb-10">
						<div class="grid grid-cols-6 gap-1.5">
							{#each shots as shot, i (shot.entry.id + ':' + shot.ref)}
								<MediaTile
									ref={shot.ref}
									onopen={() => (lightbox = { shots, index: i })}
									onhold={(x, y) => (heldMedia = { ref: shot.ref, x, y })}
								/>
							{/each}
						</div>
					</div>
				{:else}
					<PageDeck
						{pages}
						bind:index={deckIndex}
						{today}
						onopen={(s, index) => (lightbox = { shots: s, index })}
						ontoggle={onToggle}
						onassign={(entry, x, y) => (menu = { x, y, entry })}
						onholdmedia={(ref, x, y) => (heldMedia = { ref, x, y })}
						onjump={jumpTo}
						{held}
					/>
				{/if}
			</div>

			<!-- The month spine used to stand down the right edge here. Its
			     twelve bars are the index's twelve rows: two travel instruments
			     on opposite edges of one screen, for one folder, is furniture —
			     and a 5px bar is a target you aim at rather than press. The 70px
			     it held goes to the sheet. -->
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
			// The cut arrives with the name rather than being read off `held`
			// here, which by this line is a binding into a block that is being
			// torn down — see `ChapterPanel`.
			//
			// The album comes back from the write, so nothing here has to work
			// out what the change did to the chapters around it.
			act(splitChapter(folderId, at, to));
		}}
		onremove={(at) => {
			chapterPanel = null;
			// A chapter cut away while the deck is scoped to it would leave the
			// reader inside a filter that names nothing. Hand the year back
			// first; the entries are all still there.
			if (chapterParam === at) scopeTo({});
			act(unsplitChapter(folderId, at));
		}}
		onclose={() => (chapterPanel = null)}
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
				// empty — Record's block is what says so afterwards.
				act(patchFolder(owner.id, { overview_media: held.ref }));
				heldMedia = null;
			}}
		>
			Set as {owner.name}'s face
			<span class="mt-0.5 block text-[11px] font-normal text-neutral-700">
				the picture that stands for it, on Record
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
