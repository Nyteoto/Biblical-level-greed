<script lang="ts">
	/**
	 * Twelve months standing up, down the right edge of the album.
	 *
	 * This is the instrument the deleted date ruler was supposed to be and
	 * never was. The ruler showed one day at a time through a canvas of ticks;
	 * it could answer "what did I write on the 3rd" and could not answer "how
	 * much is in here", which is the question this app is now for. The spine
	 * answers the second and hands the first to the jump field.
	 *
	 * **It is the same twelve numbers as the card's sparkline** — one array,
	 * two orientations — so an album's shape on the shelf and its shape on its
	 * own screen can never disagree.
	 *
	 * Because albums restart each year the spine holds at most twelve bars,
	 * whatever the project's age. That is the entire reason the year split
	 * exists: without it this column grows a scrollbar and stops being an
	 * instrument you can read at a glance.
	 */
	import { MONTH_ABBR } from './log';

	let {
		volumes,
		live = -1,
		previousYear = null,
		onpick
	}: {
		volumes: number[];
		/** Zero-based index of the month that counts as now, or -1 in a year
		 *  that is over. */
		live?: number;
		/** The year below, if there is one. The foot of the spine hands back to
		 *  the shelf rather than ending. */
		previousYear?: string | null;
		onpick?: (month: number) => void;
	} = $props();

	const peak = $derived(Math.max(1, ...volumes));

	// Newest at the top, because that is the end you read from. Months with
	// nothing in them are left out rather than drawn flat: an empty month is
	// not a place you can scroll to.
	const months = $derived(
		volumes
			.map((n, i) => ({ month: i, n }))
			.filter((m) => m.n > 0)
			.reverse()
	);

	// History is `neutral-400` here and on the card's sparkline. The spine used
	// a lighter grey, which read as "empty" — and empty is a state the sparkline
	// draws and this column does not, because a month with nothing in it is not
	// a place you can jump to.
	const fill = (month: number) =>
		month === live
			? 'var(--gradient-spine)'
			: month === live - 1
				? 'var(--gradient-spine-last)'
				: 'var(--color-neutral-400)';
</script>

<div class="flex w-[70px] shrink-0 flex-col items-center gap-[9px] pb-[22px]">
	{#each months as m (m.month)}
		<span
			class="text-[10px] font-bold tracking-[0.14em] {m.month === live
				? 'text-accent-700'
				: 'text-neutral-700'}"
		>
			{MONTH_ABBR[m.month]}
		</span>
		<button
			type="button"
			class="w-[5px] rounded-[3px] transition-transform hover:scale-x-150"
			style="height:{Math.max(8, (m.n / peak) * 70)}px;background:{fill(m.month)};
			       box-shadow:{m.month === live ? 'var(--shadow-sm)' : 'none'}"
			title="{m.n} {m.n === 1 ? 'entry' : 'entries'}"
			aria-label="jump to {MONTH_ABBR[m.month]}"
			onclick={() => onpick?.(m.month)}
		></button>
	{/each}

	{#if previousYear}
		<a
			href="/log"
			class="mt-auto text-[10px] font-bold tracking-[0.14em] text-neutral-700 transition-colors hover:text-ink"
			style="writing-mode:vertical-rl;transform:rotate(180deg)"
			title="back to the year shelf"
		>
			{previousYear} ↑
		</a>
	{/if}
</div>
