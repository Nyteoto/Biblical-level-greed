<script lang="ts">
	/**
	 * Where you are inside this folder — the index, lying down.
	 *
	 * It was a 218px column that hid itself below 1024px and latched your
	 * choice, which is most of why the sidebar felt unpredictable: four lenses
	 * had four different left-hand columns and three different rules about when
	 * they vanished. Lying down it has no rule at all. It also leaves the
	 * reading lens with **no furniture on either side of the deck**, which is
	 * the "index collapsed" page the design was liked for.
	 *
	 * The shape is Map's chapter band, deliberately: twelve month columns with
	 * the chapters spanning across them. Two screens that draw the same twelve
	 * months should draw them the same way round, and Map's is the one that has
	 * to be horizontal, so this is the one that moves. The band itself is
	 * `ChapterBand`, which both lenses now draw — this file owns the month row
	 * above it and nothing else.
	 *
	 * Empty months are drawn and not skipped — unlike the column, which left
	 * them out. A grid whose columns are different widths stops reading as a
	 * calendar, and the whole point of twelve fixed columns is that August is
	 * always in the same place.
	 *
	 * **A chapter is started here too**, from a mark at the month of the page
	 * being read. It was `chapter starts here` in prose in the header, beside
	 * the band that draws the chapters it made — the control in one place and
	 * its result in another. The mark sits where the cut will be drawn.
	 */
	import { MONTH_ABBR } from './log';
	import ChapterBand from './ChapterBand.svelte';
	import type { AlbumView, Chapter } from './api';

	let {
		album,
		live = -1,
		month = null,
		reading = null,
		oncut,
		onpickmonth,
		onpickchapter,
		onholdchapter
	}: {
		album: AlbumView | null;
		/** Zero-based index of the month that counts as now, or -1 in a year
		 *  that is over. */
		live?: number;
		/** `YYYY-MM` when the deck is cut to a month or a chapter, so the column
		 *  that did it can mark itself. */
		month?: string | null;
		/** `YYYY-MM` of the page on screen: where the cut mark stands. */
		reading?: string | null;
		/** Start a chapter at `reading`. Absent when that month is already cut,
		 *  and then no mark is drawn — a control that does nothing is worse than
		 *  none. */
		oncut?: () => void;
		onpickmonth?: (month: number) => void;
		onpickchapter?: (chapter: Chapter) => void;
		onholdchapter?: (chapter: Chapter, x: number, y: number) => void;
	} = $props();

	const volumes = $derived(album?.volumes ?? []);
	const peak = $derived(Math.max(1, ...volumes));
	const here = $derived(month ? Number(month.slice(5, 7)) - 1 : -1);
</script>

<div class="flex min-w-0 flex-1 flex-col gap-1">
	<div class="grid min-w-0 grid-cols-12 gap-[3px]">
		{#each MONTH_ABBR as label, m (label)}
			{@const n = volumes[m] ?? 0}
			{@const on = m === here}
			<button
				type="button"
				disabled={!n}
				aria-current={on ? 'true' : undefined}
				title={n
					? `${label} · ${n} ${n === 1 ? 'entry' : 'entries'}${on ? ' — press again for the year' : ''}`
					: `${label} · nothing`}
				class="flex h-[26px] flex-col justify-end gap-[3px] px-1 pb-1 transition-colors {on
					? 'accent-fill'
					: n
						? 'hover:bg-neutral-200'
						: 'opacity-45'}"
				onclick={() => n && onpickmonth?.(m)}
			>
				<span
					class="text-[9px] leading-none font-bold tracking-[0.08em] {on
						? ''
						: m === live
							? 'text-ink'
							: 'text-neutral-600'}"
				>
					{label}
				</span>
				<!-- The volume, as the same twelve numbers the shelf's card reads.
				     A hairline at nought rather than nothing, so the twelve columns
				     keep a baseline to sit on. -->
				<span
					aria-hidden="true"
					style="height:{n ? Math.max(2, (n / peak) * 8) : 1}px;
					       background:{on
						? 'var(--color-ground)'
						: n
							? 'var(--color-neutral-600)'
							: 'var(--color-neutral-400)'}"
				></span>
			</button>
		{/each}
	</div>

	<ChapterBand
		chapters={album?.chapters ?? []}
		current={here + 1}
		cutAt={oncut && reading ? Number(reading.slice(5, 7)) : 0}
		{oncut}
		compact
		onpick={onpickchapter}
		onhold={onholdchapter}
	/>
</div>
