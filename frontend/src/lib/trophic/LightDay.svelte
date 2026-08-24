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
	import ReplyBubble from './ReplyBubble.svelte';
	import TodoEntryText from './TodoEntryText.svelte';
	import { mediaViewUrl } from './api';
	import { hold } from './hold';
	import { isVideo, plateFallback, type Shot } from './media';
	import { dayLabel } from './log';
	import type { Day } from './log';
	import type { Entry } from './api';

	let {
		day,
		onopen,
		ontoggle,
		onassign,
		onholdmedia,
		onjump,
		held = ''
	}: {
		day: Day;
		onopen?: (shots: Shot[], index: number) => void;
		ontoggle?: (entry: Entry, line: number) => void;
		onassign?: (entry: Entry, x: number, y: number) => void;
		/** The entry the reader was last sent to, marked until they look away.
		 *  See `.entry-held` — the flash says *there*, this says *this one*. */
		held?: string;
		/** Follow the thread. A reply points back at what it answers and the
		 *  original points forward at the answer, so one gesture reads both
		 *  ways — see the note on the row below. */
		onjump?: (entryId: string) => void;
		/** Hold a photograph for what can be done *with* it — the album's
		 *  overview picture. A quiet day's ribbon is where most of the log's
		 *  photographs actually are: only the newest day is a `LeadDay`, so
		 *  wiring the hero and not this left the gesture working on one day in
		 *  the year and dead on the rest. */
		onholdmedia?: (ref: string, x: number, y: number) => void;
	} = $props();

	/** A reply's attachments belong in its bubble, so they come out of the
	 *  day's strip — see `ReplyBubble`. Showing them in both places would be
	 *  the app saying the same thing twice, a rung below where it says it. */
	const strip = $derived(day.media.filter((shot) => !shot.entry.reply_to));
	/** A reply that is only a photograph never reaches `day.lines`, which keeps
	 *  entries that said something. It still has to be drawn. */
	const silentReplies = $derived(
		day.entries.filter((entry) => entry.reply_to && !entry.clean_text.trim())
	);
	/** **Newest first, which is the order `day.lines` already came in** — the
	 *  feed reads that way at every scale and a day that ran the other way
	 *  would be the one place it did not. Sorting is only needed because the
	 *  silent replies are being merged back in; getting the direction wrong
	 *  reverses every day in the log, which is exactly what it did once. */
	const rows = $derived(
		[...day.lines, ...silentReplies].sort((a, b) => b.ts.localeCompare(a.ts))
	);

	const time = (entry: Entry) =>
		new Date(entry.ts).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

</script>

<div data-day={day.key} class="flex flex-col gap-3">
	{#each rows as entry, i (entry.id)}
		<!-- `data-entry` is how the banner's reminder finds this line to scroll it
		     into the middle of the screen. Not styled, and not read by anything
		     else — it says in the DOM which entry this row is. -->
		{@const answered = !!entry.reply_to}
		{@const answeredBy = !entry.reply_to && !!entry.replied_by}
		<!-- **A reply sits on the other side of the column.** It is the one
		     shape in this log that is not a line in a list, and that is the
		     source's design: a thought you came back to weeks later reads as a
		     conversation with yourself, so the answer is set against the margin
		     the way a message you sent is. Both ends are clickable — the reply
		     jumps back to what it answers, the original jumps forward to the
		     answer — because a thread that only reads one way is a link, not a
		     thread. -->
		<div
			data-entry={entry.id}
			class="flex items-baseline gap-[18px]"
			class:flex-row-reverse={answered}
			class:entry-held={entry.id === held}
			use:hold={(x, y) => onassign?.(entry, x, y)}
		>
			<!-- The date is the thing you scan for, so it sits one rung above the
			     prose it labels; the time is metadata and sits one below. Three
			     rungs across a row that used to be one. -->
			<span
				class="w-[92px] shrink-0 text-[14px] font-bold text-neutral-800"
				class:text-right={answered}
			>
				{answered ? '' : i === 0 ? dayLabel(day.key) : ''}
			</span>
			{#if entry.todo_lines.length > 0}
				<div class="min-w-0 flex-1 text-[16px] leading-[1.5] font-light">
					<TodoEntryText {entry} ontoggle={(line) => ontoggle?.(entry, line)} />
				</div>
			{:else if answered}
				<div class="min-w-0 text-[16px] leading-[1.5] font-light">
					<ReplyBubble {entry} {onjump} {onopen} />
				</div>
			{:else if answeredBy}
				<button
					type="button"
					class="group/answered min-w-0 flex-1 text-left text-[16px] leading-[1.5] font-light text-neutral-700 transition-colors hover:text-neutral-800"
					title="jump to the reply"
					onclick={() => onjump?.(entry.replied_by)}
					style="overflow-wrap:anywhere"
				>
					<ColorizedText text={entry.clean_text} />
					<span
						class="ml-2 align-middle text-[11px] text-neutral-600 transition-colors group-hover/answered:text-accent-700"
					>
						answered ↓
					</span>
				</button>
			{:else}
				<p class="min-w-0 flex-1 text-[16px] leading-[1.5] font-light" style="overflow-wrap:anywhere">
					<ColorizedText text={entry.clean_text} />
				</p>
			{/if}
			<span class="shrink-0 font-mono text-[11px] text-neutral-600">{time(entry)}</span>
		</div>
	{/each}

	{#if strip.length}
		<div class="trophic-scrollbar-hide flex gap-[6px] overflow-x-auto pl-[110px]">
			{#each strip as shot, i (shot.entry.id + ':' + shot.ref)}
				<button
					type="button"
					class="lift lift-sm relative h-[52px] w-[72px] shrink-0 overflow-hidden rounded-[10px] bg-neutral-300 shadow-sm"
					use:hold={(x, y) => onholdmedia?.(shot.ref, x, y)}
					onclick={() => onopen?.(strip, i)}
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
