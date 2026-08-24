<script lang="ts">
	/**
	 * A run of days, read downwards: light rows, with quiet stretches merged.
	 *
	 * Why it is shaped this way
	 * -------------------------
	 * The album screen and the month screen are the same feed at two scales —
	 * the month is the album cut by day key — and they said so twice. Both
	 * derived `rows` from `foldQuiet`, both held an `expanded` set, both wrote
	 * their own `toggleStretch`, and both spelled out the same three-branch
	 * `{#each rows}` block: a day, an expanded stretch, or the strip that
	 * stands for one. Forty-seven lines on one screen and thirty-six on the
	 * other, which is the tell — they had already drifted. The strip's label
	 * column was a fixed width on the album and unconstrained on the month, and
	 * the month passed no `onassign`, no `onholdmedia` and no `held`, so
	 * holding an entry worked on one screen and drew the null ring on the next.
	 *
	 * The stretch state lives in here rather than in the routes because it is a
	 * fact about reading this feed, not about which screen is showing it: which
	 * stretches you have opened should not be something two callers can spell
	 * differently. `days` comes in already grouped because the callers need it
	 * anyway — for the contact strip, and for the line count in the header.
	 *
	 * A merge is never a hide. The strip says how many lines it is holding and
	 * expands into exactly the rows it replaced; the same days with the merge
	 * switched off in Settings render one after another unchanged.
	 */
	import LightDay from './LightDay.svelte';
	import { foldQuiet, stretchLabel, stretchTally, type Day } from './log';
	import { logSettings } from './settings.svelte';
	import type { Shot } from './media';
	import type { Entry } from './api';

	let {
		days,
		onopen,
		ontoggle,
		onjump,
		onassign,
		onholdmedia,
		held = '',
		reveal = '',
		revealed = $bindable(0)
	}: {
		days: Day[];
		onopen?: (shots: Shot[], index: number) => void;
		ontoggle?: (entry: Entry, line: number) => void;
		onjump?: (entryId: string) => void;
		/** Absent on a screen that has no assign menu to open. `LightDay`
		 *  already treats a missing handler as "this gesture is not offered
		 *  here", so there is nothing to stub. */
		onassign?: (entry: Entry, x: number, y: number) => void;
		onholdmedia?: (ref: string, x: number, y: number) => void;
		held?: string;
		/** A day key the caller needs on screen. If it is inside a folded quiet
		 *  stretch, that stretch opens.
		 *
		 *  It is a day rather than a set of open keys because the caller's
		 *  question is "show me this", not "here is my folding state" — which
		 *  stretch holds it is this component's business. A reader *sent* to a
		 *  line is one of the likeliest to be inside a fold: an overdue
		 *  reminder is old by definition, and the far end of a reply thread is
		 *  older still. Without this the jump found no row and did nothing. */
		reveal?: string;
		/** Bumped when `reveal` opened something. A caller waiting to scroll to
		 *  a row binds this so its own effect runs again once the row exists. */
		revealed?: number;
	} = $props();

	const rows = $derived(foldQuiet(days, logSettings.mergeQuiet));

	let expanded = $state<Set<string>>(new Set());

	function toggleStretch(key: string) {
		const next = new Set(expanded);
		if (next.has(key)) next.delete(key);
		else next.add(key);
		expanded = next;
	}

	$effect(() => {
		if (!reveal) return;
		const folded = rows.find(
			(row) => row.kind === 'stretch' && row.days.some((d) => d.key === reveal)
		);
		if (folded && folded.kind === 'stretch' && !expanded.has(folded.days[0].key)) {
			toggleStretch(folded.days[0].key);
			revealed += 1;
		}
	});
</script>

<div class="flex flex-col gap-3">
	{#each rows as row (row.kind === 'stretch' ? row.days[0].key : row.day.key)}
		{#if row.kind === 'day'}
			<LightDay day={row.day} {onopen} {ontoggle} {onassign} {onholdmedia} {onjump} {held} />
		{:else if expanded.has(row.days[0].key)}
			{#each row.days as day (day.key)}
				<LightDay {day} {onopen} {ontoggle} {onassign} {onholdmedia} {onjump} {held} />
			{/each}
			<button
				type="button"
				class="self-start text-[12px] font-semibold text-neutral-700 transition-colors hover:text-ink"
				onclick={() => toggleStretch(row.days[0].key)}
			>
				Collapse ▴
			</button>
		{:else}
			<!-- A merge, never a hide: the strip says how many lines it is
			     holding and expands into exactly the rows it replaced. -->
			<button
				type="button"
				class="lift lift-sm flex items-baseline gap-4 rounded-[12px] bg-surface px-4 py-[13px] text-left text-neutral-700 shadow-sm"
				onclick={() => toggleStretch(row.days[0].key)}
			>
				<span class="w-[92px] shrink-0 text-[13px] font-semibold">
					{stretchLabel(row.days)}
				</span>
				<span class="flex-1 text-[14px]">{stretchTally(row.days)}</span>
				<span class="text-[12px] font-semibold">Expand ▾</span>
			</button>
		{/if}
	{/each}
</div>
