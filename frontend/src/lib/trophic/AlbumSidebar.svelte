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
	 */
	import type { AlbumView, Folder, Shelf } from './api';
	import { holdable } from './holdable';
	import Glyph from './Glyph.svelte';

	let {
		shelf,
		album,
		folderId,
		year,
		month = null,
		oncollapse,
		onhold
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
	} = $props();

	const albumHref = (target: string | null) => `/folders/${target ?? 'unfiled'}?year=${year}`;

	/** A chapter is a run of months; opening it opens its last month, which is
	 *  where the reading picks up. */
	const chapterHref = (last: number) =>
		`/folders/${folderId ?? 'unfiled'}/${year}-${String(last).padStart(2, '0')}`;
</script>

<aside class="flex w-[252px] shrink-0 flex-col overflow-y-auto pb-6">
	<div class="flex items-baseline gap-[9px] px-[22px] pb-5">
		<span class="text-[22px] font-extrabold tracking-[-0.02em]">
			{year === 'all' ? 'All' : year}
		</span>
		<span class="flex items-center gap-1.5 text-[12px] text-neutral-700 tabular-nums">
			<Glyph kind="album" count={shelf?.albums.length ?? 0} size={12} />
			{shelf?.albums.length ?? 0}
		</span>
		<button
			type="button"
			class="ml-auto text-[16px] text-neutral-600 transition-colors hover:text-ink"
			aria-label="collapse the sidebar"
			onclick={() => oncollapse?.()}>‹</button
		>
	</div>

	<div class="mx-3 flex flex-col gap-0.5 rounded-[14px] bg-surface p-2 shadow-md">
		{#each shelf?.albums ?? [] as a (a.id)}
			{@const on = a.id === folderId}
			<a
				href={albumHref(a.id)}
				use:holdable={(x, y) => onhold?.(a, x, y)}
				class="flex items-center gap-2.5 rounded-[10px] px-3 py-[9px] transition-colors {on
					? 'accent-fill'
					: 'hover:bg-neutral-200'}"
			>
				<span class="min-w-0 flex-1 truncate {on ? 'text-[15px] font-bold' : 'text-[14px]'}">
					{a.name}
				</span>
				{#if a.state === 'shipped' && !on}
					<span class="text-[10px] font-bold tracking-[0.1em] text-neutral-700 uppercase">
						shipped
					</span>
				{:else}
					<span
						class="flex items-center gap-1.5 text-[12px] tabular-nums {on
							? 'opacity-85'
							: 'text-neutral-700'}"
					>
						<Glyph kind="entries" count={a.entry_count} size={11} />
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
				<span class="flex items-center gap-1.5 text-[12px] tabular-nums">
					<Glyph kind="entries" count={shelf.unfiled} size={11} />
					{shelf.unfiled}
				</span>
			</a>
		{/if}
	</div>

	{#if album && album.chapters.length > 0}
		<div
			class="px-[22px] pt-[26px] pb-2.5 text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase"
		>
			Chapters
		</div>
		<div class="mx-3 flex flex-col gap-2">
			{#each album.chapters as chapter (chapter.name + chapter.range)}
				<!-- A chapter is a *run* of months, so it is the one you are in
				     whenever the month falls inside it. Comparing to its last month
				     left June looking like it belonged to no chapter at all while
				     you were reading a Jun–Aug one. -->
				{@const here = month === null ? -1 : Number(month.slice(5, 7))}
				{@const on = here >= chapter.first_month && here <= chapter.last_month}
				<a
					href={chapterHref(chapter.last_month)}
					class="flex items-baseline gap-2.5 rounded-[12px] px-3.5 text-left transition-shadow {on
						? 'bg-surface py-[11px] shadow-sm'
						: 'py-[9px] hover:bg-neutral-200'}"
				>
					{#if on}
						<span
							class="w-[3px] self-stretch rounded-[2px]"
							style="background:var(--gradient-spine)"
						></span>
					{/if}
					<span class="min-w-0 flex-1 truncate text-[14px] {on ? 'font-bold' : 'text-neutral-800'}">
						{chapter.name}
					</span>
					<span class="shrink-0 text-[11px] text-neutral-700">{chapter.range}</span>
				</a>
			{/each}
		</div>
	{/if}
</aside>
