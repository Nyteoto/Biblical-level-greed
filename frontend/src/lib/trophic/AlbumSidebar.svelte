<script lang="ts">
	/**
	 * The album column: which albums exist this year, and the chapters inside
	 * the one you are reading.
	 *
	 * Extracted from the album page because the month screen needs exactly the
	 * same column — that is the point of the spike. A month is a place you go,
	 * so the chapters here are links to months rather than scroll targets, and
	 * the sidebar is the same object on both screens instead of two lists that
	 * happen to look alike.
	 *
	 * ## Two lists, both capped, both foldable
	 *
	 * This column used to be one scroll: every album, then every chapter, as
	 * long as the year happened to be. That is fine at eight folders and
	 * useless at forty — the chapters end up below the fold of a list that is
	 * itself below the fold, and the sidebar stops being the constant-cost
	 * instrument the album screen depends on.
	 *
	 * So the shelf's *groups* are here too, not only on the year shelf. A group
	 * is the arrangement you already made, and folding one is what makes a long
	 * shelf short again — the fold is the gesture that keeps this column
	 * constant-cost, and the cap on each list is the floor under it for when
	 * you have not folded anything. Scrolling inside a capped list is a
	 * fallback, not the design.
	 *
	 * The order of the headings is the shelf's, read off `shelf.groups` and
	 * written back through `onorder`. Dragging one here and dragging one on the
	 * year shelf are the same act on the same order, which is why neither
	 * screen owns it.
	 */
	import type { Album, AlbumView, Chapter, Folder, Shelf } from './api';
	import { hold } from './hold';
	import { sortable } from './sortable';
	import { albumHref, reorderGroups, splitShelf } from './shelf';
	import { collapsedChapters, collapsedGroups } from './collapsed.svelte';
	import Glyph from './Glyph.svelte';

	let {
		shelf,
		album,
		folderId,
		year,
		month = null,
		oncollapse,
		onhold,
		onholdchapter,
		onholdgroup,
		onorder
	}: {
		shelf: Shelf | null;
		album: AlbumView | null;
		folderId: string | null;
		year: string;
		/** `YYYY-MM` when a month is being read, so its chapter can mark itself. */
		month?: string | null;
		oncollapse?: () => void;
		/** Hold a row to open its properties. The row is the folder as far as
		 *  the reader is concerned, so it is the thing that answers. */
		onhold?: (folder: Folder, x: number, y: number) => void;
		/** And a chapter row answers a hold with what can be done to a chapter,
		 *  which is exactly one thing: what it is called. */
		onholdchapter?: (chapter: Chapter, x: number, y: number) => void;
		/** A group heading answers one with the same panel the year shelf opens.
		 *  The heading is the same object on both screens and a hold that works
		 *  on one and draws the null ring on the other is worse than one that
		 *  was never offered. */
		onholdgroup?: (name: string, x: number, y: number) => void;
		/** A heading was dragged into a new place. The whole order, because that
		 *  is what the log stores — see `order-groups` in eventlog.py. */
		onorder?: (order: string[]) => void;
	} = $props();


	/** A chapter is a run of months; opening it opens its last month, which is
	 *  where the reading picks up. */
	const chapterHref = (last: number) =>
		`/folders/${folderId ?? 'unfiled'}/${year}-${String(last).padStart(2, '0')}`;

	const folded = collapsedGroups();
	const chapterFold = collapsedChapters();

	/** The same cut the year shelf makes, from the same module, so the two
	 *  screens cannot disagree about what is where. */
	const loose = $derived(splitShelf(shelf).loose);
	const sections = $derived(splitShelf(shelf).sections);

	let dragging = $state<string | null>(null);
	let dropAt = $state<string | null>(null);

	function drop(name: string, before: string | null) {
		dragging = null;
		dropAt = null;
		const next = reorderGroups(shelf?.groups ?? [], name, before);
		if (next) onorder?.(next);
	}
</script>

<!-- The 34px gutter is the page's, not this component's invention: the nav
     pill sits at it on every screen, and the sidebar is what is directly
     under the pill here. It was 22 for the header and 12 for the cards,
     which put three different left edges on one screen and left the nav
     lined up with none of them. The aside owns the gutter and its children
     sit flush to it; the width grew by as much as the gutter did, so the
     cards are exactly as wide as they were.

     `overflow-hidden` rather than `overflow-y-auto`: the two lists inside
     scroll on their own now, and a third scroll around them would let the
     chapter list slide off the bottom of the screen it was capped to fit. -->
<aside class="flex w-[274px] shrink-0 flex-col overflow-hidden pb-6 pl-[34px] pr-3">
	<div class="flex shrink-0 items-baseline gap-[9px] pb-5">
		<span class="text-[22px] font-extrabold tracking-[-0.02em] text-neutral-800">
			{year === 'all' ? 'All' : year}
		</span>
		<span class="flex items-center gap-1.5 text-[12px] text-neutral-600 tabular-nums">
			<Glyph kind="album" count={shelf?.albums.length ?? 0} size={12} />
			{shelf?.albums.length ?? 0}
		</span>
		<button
			type="button"
			class="ml-auto text-[16px] text-neutral-600 transition-colors hover:text-neutral-800"
			aria-label="collapse the sidebar"
			onclick={() => oncollapse?.()}>‹</button
		>
	</div>

	{#snippet albumRow(a: Album)}
		{@const on = a.id === folderId}
		<a
			href={albumHref(a.id, year)}
			use:hold={(x, y) => onhold?.(a, x, y)}
			class="flex items-center gap-2.5 rounded-[10px] px-3 py-[9px] transition-colors {on
				? 'accent-fill'
				: 'hover:bg-neutral-200'}"
		>
			<span class="min-w-0 flex-1 truncate {on ? 'text-[15px] font-bold' : 'text-[14px]'}">
				{a.name}
			</span>
			{#if a.state === 'shipped' && !on}
				<span class="text-[10px] font-bold tracking-[0.1em] text-neutral-600 uppercase">
					shipped
				</span>
			{:else}
				<span
					class="flex items-center gap-1.5 text-[12px] tabular-nums {on
						? 'opacity-85'
						: 'text-neutral-600'}"
				>
					<Glyph kind="entries" count={a.entry_count} size={11} />
					{a.entry_count}
				</span>
			{/if}
		</a>
	{/snippet}

	<!-- The albums. As tall as the albums and no taller — `min-h-0` with the
	     default `flex-shrink` is what turns "as much as it wants" into "as much
	     as there is", so a short shelf is a short card and a long one scrolls
	     inside itself instead of pushing the chapters off the bottom. It was
	     `flex-1` for an afternoon, which stretched an empty card down the whole
	     column and did exactly that. -->
	<div
		data-sort-list="sidebar-groups"
		class="flex min-h-0 shrink flex-col gap-0.5 overflow-y-auto rounded-[14px] bg-surface p-2 shadow-md"
	>
		{#each loose as a (a.id)}
			{@render albumRow(a)}
		{/each}

		{#each sections as section (section.name)}
			{@const shut = folded.isShut(shelf?.year ?? null, section.name)}
			<!-- Where a dragged heading would land. -->
			<div
				class="mx-1 h-[2px] rounded-full transition-colors {dragging && dropAt === section.name
					? 'bg-accent-700'
					: 'bg-transparent'}"
			></div>
			<button
				type="button"
				class="group/head mt-1 flex w-full items-center gap-2 px-2 py-1.5 text-left transition-opacity {dragging ===
				section.name
					? 'opacity-50'
					: ''}"
				aria-expanded={!shut}
				use:sortable={{
					key: section.name,
					list: 'sidebar-groups',
					onhold: (x, y) => onholdgroup?.(section.name, x, y),
					onpick: () => (dragging = section.name),
					onover: (before) => (dropAt = before),
					ondrop: (before) => drop(section.name, before),
					oncancel: () => {
						dragging = null;
						dropAt = null;
					}
				}}
				onclick={() => folded.toggle(shelf?.year ?? null, section.name)}
			>
				<span
					class="inline-block text-[10px] leading-none text-neutral-600 transition-transform duration-150 group-hover/head:text-neutral-800 {shut
						? ''
						: 'rotate-90'}"
				>
					▶
				</span>
				<span
					class="min-w-0 flex-1 truncate text-[10px] font-bold tracking-[0.18em] text-neutral-600 uppercase transition-colors group-hover/head:text-neutral-800"
				>
					{section.name}
				</span>
				<span class="shrink-0 text-[11px] text-neutral-600 tabular-nums">
					{section.albums.length}
				</span>
			</button>
			{#if !shut}
				{#each section.albums as a (a.id)}
					{@render albumRow(a)}
				{/each}
			{/if}
		{/each}

		{#if dragging && dropAt === null && sections.length}
			<div class="mx-1 h-[2px] rounded-full bg-accent-700"></div>
		{/if}

		{#if shelf && shelf.unfiled > 0}
			<a
				href={albumHref(null, year)}
				class="mt-0.5 flex items-center gap-2.5 rounded-[10px] px-3 py-[9px] transition-colors {folderId ===
				null
					? 'accent-fill'
					: 'text-neutral-700 hover:bg-neutral-200'}"
			>
				<span class="min-w-0 flex-1 truncate text-[14px]">Unfiled</span>
				<span class="flex items-center gap-1.5 text-[12px] tabular-nums">
					<Glyph kind="entries" count={shelf.unfiled} size={11} />
					{shelf.unfiled}
				</span>
			</a>
		{/if}
	</div>

	{#if album && album.chapters.length > 0}
		<!-- The chapters, under their own fold and their own cap. A year can
		     hold twelve of them and the all-years view many more, and a chapter
		     list that grows until it pushes the albums off the top is the same
		     failure the groups above are here to prevent. -->
		<button
			type="button"
			class="group/ch mt-[22px] flex shrink-0 items-center gap-2 pb-2.5 text-left"
			aria-expanded={!chapterFold.shut}
			onclick={() => chapterFold.toggle()}
		>
			<span
				class="inline-block text-[10px] leading-none text-neutral-600 transition-transform duration-150 group-hover/ch:text-neutral-800 {chapterFold.shut
					? ''
					: 'rotate-90'}"
			>
				▶
			</span>
			<span
				class="text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase transition-colors group-hover/ch:text-neutral-800"
			>
				Chapters
			</span>
			<span class="text-[11px] text-neutral-600 tabular-nums">{album.chapters.length}</span>
		</button>
		{#if !chapterFold.shut}
			<!-- `shrink-0`: the chapters keep their height and the albums above
			     absorb what has to give, because the album card is the one with a
			     scrollbar in it already. Both shrinking meant both were clipped. -->
			<div class="flex max-h-[30vh] shrink-0 flex-col gap-2 overflow-y-auto">
				{#each album.chapters as chapter (chapter.name + chapter.range)}
					<!-- A chapter is a *run* of months, so it is the one you are in
					     whenever the month falls inside it. Comparing to its last month
					     left June looking like it belonged to no chapter at all while
					     you were reading a Jun–Aug one. -->
					{@const here = month === null ? -1 : Number(month.slice(5, 7))}
					{@const on = here >= chapter.first_month && here <= chapter.last_month}
					<a
						href={chapterHref(chapter.last_month)}
						use:hold={(x, y) => onholdchapter?.(chapter, x, y)}
						class="flex shrink-0 items-baseline gap-2.5 rounded-[12px] px-3.5 text-left transition-shadow {on
							? 'bg-surface py-[11px] shadow-sm'
							: 'py-[9px] hover:bg-neutral-200'}"
					>
						{#if on}
							<span
								class="w-[3px] self-stretch rounded-[2px]"
								style="background:var(--gradient-spine)"
							></span>
						{/if}
						<span class="min-w-0 flex-1 truncate text-[14px] {on ? 'font-bold text-neutral-800' : 'text-neutral-700'}">
							{chapter.name}
						</span>
						<span class="shrink-0 text-[11px] text-neutral-600">{chapter.range}</span>
					</a>
				{/each}
			</div>
		{/if}
	{/if}
</aside>
