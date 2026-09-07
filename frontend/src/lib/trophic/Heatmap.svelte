<script lang="ts">
	/**
	 * A year of one folder, one cell per day, brighter where more happened.
	 *
	 * ## What a cell is worth
	 *
	 * **One point per entry, one point per twenty minutes clocked.** The server
	 * does that arithmetic — see `points` in `index.py` — and what arrives here
	 * is the count plus the two halves it came from, so a pressed cell can say
	 * where its points came from rather than only how many there were.
	 *
	 * An entry counts the same whether it is a word or a paragraph. That is the
	 * same refusal the rest of the app makes: nothing here has ever had an
	 * opinion about how much you wrote, and a heatmap that weighed length would
	 * be the first thing that did.
	 *
	 * ## Why the ramp is analog, and why it stops
	 *
	 * GitHub and Anki both quantise — five buckets, five swatches — because
	 * they are drawing many people's years at a glance and a bucket is easier
	 * to compare across strangers. This is one person's one project, and the
	 * interesting reading is *this week against last week*, which a bucket
	 * boundary destroys: eleven points and twenty points are the same square.
	 * So the brightness is continuous in the score, and the only structure in
	 * the ramp is where it starts and where it ends.
	 *
	 * It ends at `PEAK` points. Past that the cell is simply lit, and the extra
	 * points are still counted — they are still in the readout, and they still
	 * order the shelf. A ramp with no ceiling would have one enormous day set
	 * the scale for the year and render eleven ordinary months as ground; a
	 * ceiling that also *discarded* what it clipped would make the readout
	 * disagree with the number the shelf sorted on. Clipping the light and
	 * keeping the count is the only arrangement where both stay honest.
	 *
	 * `FLOOR` is the other end and matters as much: a single entry is 1/10th of
	 * the way up a linear ramp, which on this ground is indistinguishable from
	 * an empty day. A day you touched must not read as a day you did not, so
	 * the ramp starts at a rung that is already visibly lit and climbs from
	 * there. The scale is legible because the ceiling is fixed, not because the
	 * bottom is dark.
	 *
	 * ## Layout
	 *
	 * Weeks are columns, days are rows, Mondays on top — the app counts weeks
	 * from Monday everywhere else (`albumWeek`), and a heatmap that started its
	 * weeks on Sunday would be the one place it did not.
	 *
	 * The grid is drawn from the calendar, not from the data: the server sends
	 * only days with something on them, because a year is 365 cells and posting
	 * the empty ones is posting a calendar the client can already work out.
	 *
	 * It carries no heading of its own. `JAN … DEC` along the top says what it
	 * is, the `Readings` label above says what kind of thing it is, and the
	 * `\pattern` bars beside it are unlabelled for the same reason — a word
	 * here would restate the year a third time and push the grid one line below
	 * the bars it is meant to sit level with.
	 */
	import { MONTH_ABBR } from './log';
	import { duration } from './timer';
	import type { HeatDay } from './api';

	let {
		year,
		heat = [],
		today = ''
	}: {
		/** The year on screen, or null when the year setting is off. Null draws
		 *  a rolling twelve months ending today rather than nothing: `all` means
		 *  "do not restart the album each January", not "do not have a scale",
		 *  and every year at once is either unreadably wide or a different
		 *  chart. Either way the grid is 52 or 53 columns and reads the same. */
		year: string | null;
		heat?: HeatDay[];
		/** Today's day key, so the current day can be marked. Passed in rather
		 *  than read from a clock here, for the reason every other date in this
		 *  app is: one place knows what day it is. */
		today?: string;
	} = $props();

	/** Where the ramp tops out. Ten is a heavy day — ten entries, or three and
	 *  a half hours at the desk, or any mixture — and days past it are rare
	 *  enough that spending the whole scale on them would flatten the year. */
	const PEAK = 10;
	/** The two ends of the ramp, as RGB. `FLOOR` is `--color-accent-400`, the
	 *  dimmest rung that still reads as lit; the top is the phosphor itself.
	 *  Written out rather than read from the custom properties because these
	 *  are interpolated numerically, and `color-mix` is not a thing this app
	 *  relies on the packaged engine having. */
	const FLOOR = [45, 143, 90];
	const LIT = [79, 255, 159];
	/** A cell and its gap, in px. The month strip is positioned off this, so
	 *  the two have to agree — a label that drifts a week by December is worse
	 *  than no label. */
	const PITCH = 11;

	/** Continuous, and clipped at both ends. `t` is where in the ramp a day
	 *  sits; the colour is the straight line between the two rungs. */
	function glow(points: number): string {
		const t = Math.min(1, Math.max(0, (points - 1) / (PEAK - 1)));
		const mix = FLOOR.map((c, i) => Math.round(c + (LIT[i] - c) * t));
		return `rgb(${mix[0]} ${mix[1]} ${mix[2]})`;
	}

	/** Days with something on them, by key. A day whose only activity was a
	 *  short session is in here with `points` of 0 — it is still a day you
	 *  worked, and pressing it still says so. */
	const scored = $derived(new Map(heat.map((d) => [d.day, d])));

	function key(date: Date): string {
		return date.toISOString().slice(0, 10);
	}

	/** The two ends of the grid. A named year is its own January to December;
	 *  no year is the twelve months behind today. */
	const span = $derived.by((): [Date, Date | null] => {
		if (year) {
			return [new Date(Date.UTC(Number(year), 0, 1)), new Date(Date.UTC(Number(year), 11, 31))];
		}
		if (!today) return [new Date(0), null];
		const [y, m, d] = today.split('-').map(Number);
		const end = new Date(Date.UTC(y, m - 1, d));
		const start = new Date(end);
		start.setUTCDate(start.getUTCDate() - 364);
		return [start, end];
	});

	/**
	 * The calendar, as columns of seven. The first column starts on the Monday
	 * on or before the first day of the span, and the last column runs to the
	 * Sunday after its last, so every column is a whole week and the rows line
	 * up. Days outside the span are null and draw nothing — they hold the
	 * shape rather than leaving a ragged corner.
	 *
	 * Built in UTC throughout. There is no timezone question here: a day key
	 * arrives already resolved in the user's zone, and doing the arithmetic in
	 * local time is how a grid ends up shifted by one row for half the year.
	 */
	const weeks = $derived.by(() => {
		const [first, last] = span;
		if (!last) return [];
		const cursor = new Date(first);
		// Monday = 0, which is the offset back to the start of the column.
		cursor.setUTCDate(cursor.getUTCDate() - ((cursor.getUTCDay() + 6) % 7));

		const out: (string | null)[][] = [];
		while (cursor <= last) {
			const column: (string | null)[] = [];
			for (let row = 0; row < 7; row++) {
				column.push(cursor >= first && cursor <= last ? key(cursor) : null);
				cursor.setUTCDate(cursor.getUTCDate() + 1);
			}
			out.push(column);
		}
		return out;
	});

	/** Which column each month opens in, for the strip of labels along the top.
	 *  A month is labelled once, over the week its 1st falls in. */
	const months = $derived(
		weeks
			.map((column, index) => {
				const opens = column.find((day) => day && day.endsWith('-01'));
				return opens ? { index, label: MONTH_ABBR[Number(opens.slice(5, 7)) - 1] } : null;
			})
			.filter((m): m is { index: number; label: string } => m !== null)
	);

	/** The pressed day. One at a time, and pressing it again puts it away —
	 *  a readout that can only be opened is a readout that is always on. */
	let picked = $state<string | null>(null);
	const reading = $derived(picked ? (scored.get(picked) ?? null) : null);

	/** `Sat 12 Aug`. Long enough to place the cell you pressed, short enough to
	 *  sit on one line with the counts. No year: the screen around this states
	 *  it twice already. */
	function label(day: string): string {
		const [y, m, d] = day.split('-').map(Number);
		return new Date(y, m - 1, d).toLocaleDateString(undefined, {
			weekday: 'short',
			day: 'numeric',
			month: 'short'
		});
	}

	/** What a day is worth, said in full. The hover title and the pressed
	 *  readout are the same sentence — there is one right way to say this. */
	function says(day: string): string {
		const found = scored.get(day);
		if (!found) return `${label(day)} — nothing`;
		const parts: string[] = [];
		if (found.entries) parts.push(`${found.entries} ${found.entries === 1 ? 'entry' : 'entries'}`);
		if (found.seconds) parts.push(duration(found.seconds));
		return `${label(day)} — ${found.points} ${found.points === 1 ? 'point' : 'points'} · ${parts.join(' · ')}`;
	}
</script>

{#if weeks.length > 0}
	<div class="flex min-w-0 flex-col gap-2">
		<!-- The grid scrolls sideways rather than shrinking its cells. Fifty-three
		     weeks is a real width and a heatmap squeezed under it stops being
		     readable before it stops fitting. -->
		<div class="min-w-0 overflow-x-auto pb-1">
			<div class="inline-flex flex-col gap-[3px]">
				<div class="relative h-[10px]">
					{#each months as month (month.index)}
						<span
							class="absolute top-0 text-[9px] leading-[10px] font-bold tracking-[0.1em] text-neutral-600"
							style="left:{month.index * PITCH}px"
						>
							{month.label}
						</span>
					{/each}
				</div>

				<div class="flex gap-[2px]">
					{#each weeks as column, w (w)}
						<div class="flex flex-col gap-[2px]">
							{#each column as day, d (d)}
								{#if day === null}
									<div class="h-[9px] w-[9px]"></div>
								{:else}
									{@const found = scored.get(day)}
									{@const points = found?.points ?? 0}
									<!-- Outlined rather than ringed: the marks sit in a 2px
									     gap, and an outline is the one border that costs no
									     layout and can be offset outward by exactly 1px.
									     Today is marked dimly and always; the pressed cell
									     takes the accent, and takes it back from today when
									     they are the same square. -->
									<button
										type="button"
										title={says(day)}
										aria-label={says(day)}
										aria-pressed={picked === day}
										class="h-[9px] w-[9px] rounded-[2px]"
										style="background:{points > 0
											? glow(points)
											: 'var(--color-neutral-200)'};{picked === day
											? 'outline:1px solid var(--color-accent-700);outline-offset:1px'
											: day === today
												? 'outline:1px solid var(--color-neutral-500)'
												: ''}"
										onclick={() => (picked = picked === day ? null : day)}
									></button>
								{/if}
							{/each}
						</div>
					{/each}
				</div>
			</div>
		</div>

		<!-- The readout. It holds its line whether or not anything is pressed,
		     because a row of cells that reflows the block under it every time you
		     press one is a grid you cannot compare two days in. -->
		<div class="min-h-[16px] text-[11px] leading-[16px] text-neutral-700 tabular-nums">
			{#if picked}
				<!-- Separated by margin rather than by spaces inside the dividers:
				     the whitespace at a tag's edge is the compiler's to collapse,
				     and it collapsed exactly one side of every `·` here. -->
				<span class="text-neutral-800">{label(picked)}</span>
				<span class="mx-1.5 text-neutral-600">—</span>
				{#if reading}
					<span style="color:var(--color-accent-700)">
						{reading.points}
						{reading.points === 1 ? 'point' : 'points'}
					</span>
					{#if reading.entries}
						<span class="mx-1.5 text-neutral-600">·</span>
						<span>{reading.entries} {reading.entries === 1 ? 'entry' : 'entries'}</span>
					{/if}
					{#if reading.seconds}
						<span class="mx-1.5 text-neutral-600">·</span>
						<span>{duration(reading.seconds)}</span>
					{/if}
				{:else}
					<span>nothing</span>
				{/if}
			{/if}
		</div>
	</div>
{/if}
