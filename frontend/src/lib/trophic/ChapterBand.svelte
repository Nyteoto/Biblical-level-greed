<script lang="ts">
	/**
	 * A folder's chapters, drawn as spans across twelve month columns.
	 *
	 * This was written twice — once inside `MonthBand`, once inline in Map —
	 * and the two copies had already drifted on the one thing the band says
	 * beyond its names: **which chapter is the current one**. `MonthBand` lit
	 * the chapter containing the month the deck is cut to; Map lit the one
	 * containing today, and did not check that the year on screen was this
	 * year at all, so a 2019 album lit whichever chapter covered September.
	 * Reading May on the deck, Map still pointed at September.
	 *
	 * That is the `folders/[id]/[month]` failure exactly — two screens holding
	 * their own copy of one drawing, agreeing until they quietly did not —
	 * reproduced inside the step that was deleting it. So the reversal, the
	 * span arithmetic, the unnamed-chapter fallback and the inset rule live
	 * here, and the difference between the two lenses is the one prop that
	 * *is* the difference.
	 *
	 * **Oldest first, and only here.** Every other list in this app reads
	 * newest first, and so does `chapters` — but a grid places items in source
	 * order and pushes one whose column sits *behind* the cursor onto a new
	 * row, so newest-first drew three chapters as three stacked bands. This
	 * band is spatial rather than a list: its order is the calendar's.
	 *
	 * Interactive only when asked: Map measures and takes you somewhere, so
	 * its band is spans. The reading lens picks and holds, so its band is
	 * buttons. `hold` is attached in the one case because `data-hold` says in
	 * the DOM that a node has properties, and a band that cannot be held
	 * should not claim it can.
	 *
	 * **The cut mark** is the one thing here that is not a chapter: a short
	 * dashed rule at the start of a month, where a new cut would begin. Only
	 * the reading lens asks for it. Every item is pinned to the first row, so
	 * the mark can stand over a chapter that already covers its month —
	 * which is exactly the case where cutting splits one — without the grid
	 * pushing it onto a row of its own.
	 */
	import { hold } from './hold';
	import type { Chapter } from './api';

	let {
		chapters,
		current = 0,
		compact = false,
		cutAt = 0,
		oncut,
		onpick,
		onhold
	}: {
		chapters: Chapter[];
		/** The month that counts as current *in the year on screen*, 1-based,
		 *  or 0 for none. Which month that is belongs to the lens: the deck's
		 *  open page on the reading lens, today on Map — and today only while
		 *  the year on screen is the one today is in. */
		current?: number;
		/** The reading lens sits this under the month row and wants it tight;
		 *  Map has the room. */
		compact?: boolean;
		/** 1-based month to draw the cut mark at, or 0 for none. */
		cutAt?: number;
		oncut?: () => void;
		onpick?: (chapter: Chapter) => void;
		onhold?: (chapter: Chapter, x: number, y: number) => void;
	} = $props();

	const band = $derived([...chapters].reverse());
	const interactive = $derived(Boolean(onpick || onhold));

	const covers = (c: Chapter) =>
		current > 0 && current >= c.first_month && current <= c.last_month;

	/** Cut and not yet named: the range stands in for the name, here as
	 *  everywhere. Nothing in this app invents a word for one. */
	const label = (c: Chapter) => c.name || c.range;

	const cls = (on: boolean) =>
		`flex items-center truncate text-left transition-colors ${
			compact ? 'h-[18px] pl-1.5 text-[10px]' : 'h-6 pl-2 text-[11px]'
		} ${on ? 'text-ink' : interactive ? 'text-neutral-600 hover:text-ink' : 'text-neutral-600'}`;

	const style = (c: Chapter, on: boolean) =>
		`grid-row: 1; grid-column: ${c.first_month} / span ${c.last_month - c.first_month + 1};` +
		`box-shadow:inset 2px 0 0 0 ${on ? 'var(--color-accent)' : 'var(--color-neutral-500)'}`;
</script>

{#if band.length || (cutAt > 0 && oncut)}
	<div class="grid min-w-0 grid-cols-12 {compact ? 'gap-[3px]' : 'gap-1'}">
		{#each band as chapter (chapter.month)}
			{@const on = covers(chapter)}
			{#if interactive}
				<button
					type="button"
					class={cls(on)}
					style={style(chapter, on)}
					title="{chapter.name || 'unnamed'} · {chapter.range}"
					use:hold={(x, y) => onhold?.(chapter, x, y)}
					onclick={() => onpick?.(chapter)}
				>
					<span class="truncate">{label(chapter)}</span>
				</button>
			{:else}
				<span
					class={cls(on)}
					style={style(chapter, on)}
					title="{chapter.name || 'unnamed'} · {chapter.range}"
				>
					<span class="truncate">{label(chapter)}</span>
				</span>
			{/if}
		{/each}
		{#if cutAt > 0 && oncut}
			<!-- Above the chapter it would split, and small: it begins the
			     month's cell rather than filling it, so a chapter's name running
			     through that month is still readable past it. -->
			<button
				type="button"
				class="cut-mark relative z-10 flex items-center justify-center self-stretch justify-self-start
				       {compact ? 'h-[18px] w-[18px] text-[12px]' : 'h-6 w-6 text-[13px]'}"
				style="grid-row: 1; grid-column: {cutAt} / span 1"
				title="start a chapter here"
				aria-label="start a chapter here"
				onclick={oncut}
			>
				+
			</button>
		{/if}
	</div>
{/if}

<style>
	/* Dashed where a chapter's edge is solid: a cut that could be, drawn in
	   the shape of the ones that are. On the ground so it reads over a
	   chapter's name rather than through it. */
	.cut-mark {
		color: var(--color-neutral-600);
		background: var(--color-ground);
		border-left: 2px dashed var(--color-neutral-500);
		transition: color 150ms ease-out, border-color 150ms ease-out;
	}
	.cut-mark:hover {
		color: var(--color-ink);
		border-left-color: var(--color-accent);
	}
</style>
