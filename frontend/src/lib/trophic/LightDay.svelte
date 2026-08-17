<script lang="ts">
	/**
	 * A day below the lead: a date, its lines, and the times they were written.
	 * No card, no rule, no photograph at full size — the whole point of the
	 * shape is that yesterday costs one line and last week costs one line each.
	 *
	 * The date sits on the first row only. Repeating it down a day with four
	 * lines would turn a list into a table, and the eye already knows.
	 *
	 * A light day that *does* have media gets a small ribbon under its rows.
	 * The design's frame shows only text days here, but a day is not allowed to
	 * quietly lose a photograph because it was not the newest one — the tile is
	 * how you find out it is there, and tapping it opens the same lightbox the
	 * lead day does.
	 */
	import ColorizedText from './ColorizedText.svelte';
	import TodoEntryText from './TodoEntryText.svelte';
	import { longpress } from './longpress';
	import { mediaViewUrl } from './api';
	import { isVideo, plateFallback, type Shot } from './media';
	import { dayLabel } from './log';
	import type { Day } from './log';
	import type { Entry } from './api';

	let {
		day,
		onopen,
		ontoggle,
		onassign
	}: {
		day: Day;
		onopen?: (shots: Shot[], index: number) => void;
		ontoggle?: (entry: Entry, line: number) => void;
		onassign?: (entry: Entry, x: number, y: number) => void;
	} = $props();

	const time = (entry: Entry) =>
		new Date(entry.ts).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

</script>

<div data-day={day.key} class="flex flex-col gap-3">
	{#each day.lines as entry, i (entry.id)}
		<div class="flex items-baseline gap-[18px]" use:longpress={(x, y) => onassign?.(entry, x, y)}>
			<span class="w-[92px] shrink-0 text-[14px] font-bold">
				{i === 0 ? dayLabel(day.key) : ''}
			</span>
			{#if entry.todo_lines.length > 0}
				<div class="min-w-0 flex-1 text-[16px] leading-[1.5] font-light">
					<TodoEntryText {entry} ontoggle={(line) => ontoggle?.(entry, line)} />
				</div>
			{:else}
				<p class="min-w-0 flex-1 text-[16px] leading-[1.5] font-light" style="overflow-wrap:anywhere">
					<ColorizedText text={entry.clean_text} />
				</p>
			{/if}
			<span class="shrink-0 font-mono text-[11px] text-neutral-700">{time(entry)}</span>
		</div>
	{/each}

	{#if day.media.length}
		<div class="trophic-scrollbar-hide flex gap-[6px] overflow-x-auto pl-[110px]">
			{#each day.media as shot, i (shot.entry.id + ':' + shot.ref)}
				<button
					type="button"
					class="lift lift-sm relative h-[52px] w-[72px] shrink-0 overflow-hidden rounded-[10px] bg-neutral-300 shadow-sm"
					onclick={() => onopen?.(day.media, i)}
					aria-label={isVideo(shot.ref) ? 'play clip' : 'open photo'}
				>
					<img
						src={mediaViewUrl(shot.ref)}
						alt=""
						loading="lazy"
						decoding="async"
						onerror={(e) => plateFallback(e, shot.ref)}
						class="h-full w-full object-cover"
					/>
					{#if isVideo(shot.ref)}
						<span
							class="absolute bottom-1 left-1 rounded-[5px] bg-ground/85 px-[5px] py-[2px] font-mono text-[8px] text-neutral-800"
						>
							▶
						</span>
					{/if}
				</button>
			{/each}
		</div>
	{/if}
</div>
