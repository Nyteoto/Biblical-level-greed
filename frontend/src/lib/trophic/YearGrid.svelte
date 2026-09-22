<script lang="ts">
	/**
	 * A year as twelve columns and thirty-one rows.
	 *
	 * ## Why this shape and not the other one
	 *
	 * The heatmap this replaces was the GitHub arrangement — 53 week-columns of
	 * seven days, Mondays on top. That shape answers "how consistent have I
	 * been", which is a question about *rhythm*, and it answers it well.
	 *
	 * This one answers "what did the year look like", which is a question about
	 * *shape*: which months were heavy, where the gaps fell, how a stretch of
	 * work sits against the calendar everyone else uses. A month is a column you
	 * can point at, the 3rd of May is somewhere you can find, and a chapter can
	 * be drawn as a span across the top because the columns *are* months.
	 *
	 * It also fits. 12 × 31 is 372 cells in a block twelve wide; 53 × 7 is the
	 * same count in a block fifty-three wide, which is wider than a tablet and
	 * has to scroll sideways — and a year you have to scroll is not an
	 * instrument, it is a document.
	 *
	 * ## Four states, and why the dead ones are drawn at all
	 *
	 *   - **absent** — the 31st of a 30-day month. Transparent, but it holds its
	 *     cell, because a grid whose columns are different lengths stops being
	 *     readable as a calendar.
	 *   - **nothing** — a day that happened and holds nothing. It is the ramp's
	 *     own floor, so one entry is the first rung *up* from it. Drawing it
	 *     any brighter makes an empty year and a busy one the same picture,
	 *     which is what the first cut of this did.
	 *   - **ahead** — later this year, and darker than nothing: an October you
	 *     have not reached and an October you did nothing in are different
	 *     facts, and only one of them is about you.
	 *   - **lit** — the ramp, by points.
	 *
	 * The ramp stops one rung below white. **White means the current thing** —
	 * today's ring, the selected cell — and a heavy day is not that.
	 */
	import { MONTH_ABBR } from './log';
	import { dateLabel } from './day';

	let {
		year,
		days = [],
		today = '',
		selected = '',
		onpick
	}: {
		/** `YYYY`. The all-years view has no grid to draw — twelve columns of
		 *  every year at once is not a shape — so the caller does not render
		 *  this then. */
		year: string;
		/** Only days with something on them, which is what the server sends. */
		days?: { day: string; entries: number; seconds: number; points: number }[];
		today?: string;
		selected?: string;
		onpick?: (day: string) => void;
	} = $props();

	/** Where the ramp tops out. Ten points is a heavy day — ten entries, or
	 *  three and a half hours, or any mixture — and a day past it is simply at
	 *  the top. Same number the old grid used, because it is the same rule. */
	const PEAK = 10;
	/**
	 * Seven lit rungs over the floor, ending below white.
	 *
	 * **The steps widen as they climb**, 7–12 points of lightness apart rather
	 * than an even 4–6. The first cut spent its range evenly and started one
	 * hair above the floor, so a one-point day was barely told from nothing and
	 * the bottom three rungs read as one colour — on a real year only about
	 * three steps could be seen at all, and the heavy days did not stand out
	 * from the ordinary ones. The mapping below is untouched; only the paint
	 * moved. Lightness in HSL at a fixed slate hue, so the rungs differ in one
	 * dimension and nothing else.
	 */
	const EMPTY = '#171b1f';
	const AHEAD = '#12161a';
	const RAMP = [
		'#2c343a',
		'#3c464e',
		'#4e5b65',
		'#62737f',
		'#7d8f9b',
		'#a0adb6',
		'#c2cbd0'
	];

	const DIM = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];

	const scored = $derived(new Map(days.map((d) => [d.day, d])));
	/** A leap February gets its 29th; nothing else in here cares what year it
	 *  is, which is why this is the only place the year is arithmetic. */
	const lengths = $derived.by(() => {
		const y = Number(year);
		const out = [...DIM];
		if ((y % 4 === 0 && y % 100 !== 0) || y % 400 === 0) out[1] = 29;
		return out;
	});

	const key = (month: number, day: number) =>
		`${year}-${String(month + 1).padStart(2, '0')}-${String(day + 1).padStart(2, '0')}`;

	function fill(points: number): string {
		const t = Math.min(1, Math.max(0, (points - 1) / (PEAK - 1)));
		return RAMP[Math.min(RAMP.length - 1, Math.round(t * (RAMP.length - 1)))];
	}

	/** What a cell says when it is pressed or hovered. One sentence, and the
	 *  same one for the pointer and the screen reader. */
	function says(dayKey: string): string {
		const found = scored.get(dayKey);
		const label = dateLabel(dayKey);
		if (!found) return `${label} — nothing`;
		const parts: string[] = [];
		if (found.entries) parts.push(`${found.entries} ${found.entries === 1 ? 'entry' : 'entries'}`);
		if (found.seconds) parts.push(`${Math.round(found.seconds / 60)} minutes`);
		return `${label} — ${found.points} ${found.points === 1 ? 'point' : 'points'}${
			parts.length ? ' · ' + parts.join(' · ') : ''
		}`;
	}
</script>

<div class="flex min-w-0 flex-col gap-2">
	<!-- The month heads. The current one is the only lit thing up here. -->
	<div class="flex gap-2.5">
		<span class="w-[26px] shrink-0"></span>
		<div class="grid min-w-0 flex-1 grid-cols-12 gap-1">
			{#each MONTH_ABBR as name, m (name)}
				<span
					class="truncate text-center text-[11px] font-bold tracking-[0.1em] uppercase {today.slice(
						0,
						7
					) === `${year}-${String(m + 1).padStart(2, '0')}`
						? 'text-ink'
						: 'text-neutral-600'}"
				>
					{name}
				</span>
			{/each}
		</div>
	</div>

	<div class="flex min-w-0 gap-2.5">
		<!-- The ruler. Every fifth, and the 1st, because a number on every row
		     is 31 numbers competing with 372 cells. -->
		<div class="flex w-[26px] shrink-0 flex-col gap-[3px]">
			{#each Array(31) as _, d (d)}
				<span
					class="flex h-[15px] items-center justify-end text-[9px] text-neutral-500 tabular-nums"
				>
					{d === 0 || (d + 1) % 5 === 0 ? d + 1 : ''}
				</span>
			{/each}
		</div>

		<div class="flex min-w-0 flex-1 flex-col gap-[3px]">
			{#each Array(31) as _, d (d)}
				<div class="grid min-w-0 grid-cols-12 gap-1">
					{#each Array(12) as _, m (m)}
						{@const exists = d < lengths[m]}
						{@const cell = exists ? key(m, d) : ''}
						{@const ahead = exists && !!today && cell > today}
						{@const found = exists ? scored.get(cell) : undefined}
						{#if !exists}
							<span class="h-[15px]"></span>
						{:else}
							<button
								type="button"
								title={says(cell)}
								aria-label={says(cell)}
								aria-pressed={selected === cell}
								class="h-[15px] transition-opacity hover:opacity-80"
								style="background:{ahead
									? AHEAD
									: found && found.points > 0
										? fill(found.points)
										: EMPTY};{selected === cell
									? 'outline:2px solid var(--color-accent);outline-offset:-2px'
									: cell === today
										? 'outline:1px solid var(--color-accent)'
										: ''}"
								onclick={() => onpick?.(cell)}
							></button>
						{/if}
					{/each}
				</div>
			{/each}
		</div>
	</div>
</div>
