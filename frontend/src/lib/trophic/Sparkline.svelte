<script lang="ts">
	/**
	 * Twelve months of an album, lying down. The same list the month spine
	 * stands up on the album screen — one array, two orientations, so a card
	 * and the screen it opens can never disagree about when a project was busy.
	 *
	 * Bars are scaled against the album's *own* peak, not against the shelf's.
	 * A quiet project next to a busy one would otherwise be a flat line, and
	 * the question this answers is "when was this one busy", not "is this one
	 * busier than that one" — the entry counts underneath already answer that.
	 *
	 * The three-band colouring is the same idea: this month lives, last month
	 * is fading, everything before is history. It is not a heat map.
	 */
	let {
		volumes,
		live = -1
	}: {
		volumes: number[];
		/** Zero-based index of the month that counts as now. `-1` for a year
		 *  that is over, where nothing is live and the whole row is history. */
		live?: number;
	} = $props();

	const peak = $derived(Math.max(1, ...volumes));

	// A month with nothing in it still draws a stub. A gap would read as "this
	// part of the year does not exist", and it does — you just did not write.
	const height = (n: number) => (n === 0 ? 6 : Math.max(10, (n / peak) * 100));

	// The same four fills the month spine uses, from the same two variables. A
	// hand-rolled gradient here had drifted a shade darker than the spine's, so
	// last month looked like one thing on the shelf and another on the screen
	// the card opens — which is precisely what "one array, two orientations"
	// was supposed to make impossible.
	const fill = (i: number, n: number) =>
		n === 0
			? 'var(--color-neutral-300)'
			: i === live
				? 'var(--gradient-spine)'
				: i === live - 1
					? 'var(--gradient-spine-last)'
					: 'var(--color-neutral-400)';
</script>

<div class="flex h-[34px] items-end gap-[3px]" aria-hidden="true">
	{#each volumes as n, i (i)}
		<span
			class="flex-1 rounded-[2px]"
			style="height:{height(n)}%;background:{fill(i, n)}"
		></span>
	{/each}
</div>
