<script lang="ts">
	/**
	 * One page of the diary: a day, given the whole treatment.
	 *
	 * This is `LeadDay` generalised. That component dressed exactly one day —
	 * the newest — because three hundred of them shared one scroll and only the
	 * top of it could afford a photograph at size. A deck of pages removes that
	 * pressure: every day is the only thing on screen while you are on it, so
	 * every day gets its plate, its caption and its lines. The compact row that
	 * every other day used to get existed for a constraint that is gone.
	 *
	 * The order inside a page is `LeadDay`'s and the argument is unchanged: the
	 * photographs first, then what was said about the first of them, then the
	 * remaining lines. You recognise a day by the picture and read the words
	 * once you have found it.
	 *
	 * ## Two sizes of photograph, and no third
	 *
	 * One photograph goes the full width of the sheet; two or three share a row
	 * at equal size; more than three are rows of three, the last tile saying
	 * how many are left. It was a 250px hero and a strip of 96px thumbnails —
	 * a jump from the whole sheet straight to a postage stamp, with nothing
	 * between, so the second-best photograph of a day was drawn at a
	 * fourteenth of the size of the first. Which photograph leads is still
	 * `paginate`'s; this only decides how big they are.
	 *
	 * ## Every line has its time on the left
	 *
	 * The caption had no time, a reply had its time on the right because the
	 * whole row was mirrored, and a todo had it on the left — three places for
	 * one fact on one page. Every line now has the same gutter, always on the
	 * left, the caption included. The reply bubble's rounded shape is what says
	 * it is an answer; it does not need the margin as well.
	 *
	 * **It draws what it is given and works nothing out.** The hero, the caption
	 * promoted out of the list, the silent replies merged back in, and which
	 * lines belong to this part of a heavy day are all decided by `paginate` in
	 * `log.ts`, where a local check can hold them to never dropping a line. A
	 * second reckoning of that in here is a second chance to lose one.
	 *
	 * **The sheet is not this component's.** `PageDeck` draws it — the surface,
	 * the radius, the edge — and this prints on it. That inversion is what
	 * makes a pile possible: sheets have to be the same object at the same size
	 * before their edges can stack behind one another, and a component as tall
	 * as its own content can never be that. What is left here is the printing,
	 * which is what it was always for.
	 */
	import ColorizedText from './ColorizedText.svelte';
	import ReplyBubble from './ReplyBubble.svelte';
	import TodoEntryText from './TodoEntryText.svelte';
	import { mediaViewUrl } from './api';
	import { hold } from './hold';
	import Glyph from './Glyph.svelte';
	import { isVideo, plateFallback, type Shot } from './media';
	import { dayLabel, type Page } from './log';
	import { clockLabel, weekdayLabel } from './day';
	import type { Entry } from './api';

	let {
		page,
		today = false,
		onopen,
		onholdmedia,
		onjump,
		ontoggle,
		onassign,
		held = ''
	}: {
		page: Page;
		today?: boolean;
		onopen?: (shots: Shot[], index: number) => void;
		/** Hold a photograph for what can be done *with* it — the album's
		 *  overview picture. */
		onholdmedia?: (ref: string, x: number, y: number) => void;
		/** Follow the thread, both ways. See `ReplyBubble`. */
		onjump?: (entryId: string) => void;
		ontoggle?: (entry: Entry, line: number) => void;
		onassign?: (entry: Entry, x: number, y: number) => void;
		/** The entry the reader was last sent to, marked until they look away. */
		held?: string;
	} = $props();

	/** Two rows of three before the last tile turns into a count. The rest are
	 *  one press away in the lightbox, which pages through all of them. */
	const PLATES = 6;

	const time = (entry: Entry) => clockLabel(entry.ts);

	/** Every photograph on this part of the day, in `page.shots` order — so
	 *  a tile's index here is its index in the lightbox. */
	const plates = $derived(page.hero ? [page.hero, ...page.ribbon] : []);
	const shown = $derived(plates.slice(0, PLATES));
	const hidden = $derived(plates.length - shown.length);
	/** One across, or up to three. */
	const across = $derived(plates.length === 1 ? 1 : plates.length === 2 ? 2 : 3);
</script>

<article
	data-day={page.day.key}
	data-page={page.key}
	class="flex flex-col gap-[18px] px-4 py-5 sm:px-[30px] sm:py-[26px]"
>
	<div class="flex items-baseline gap-3.5">
		<h2 class="text-[34px] leading-none font-extrabold tracking-[-0.03em]">
			{dayLabel(page.day.key)}
		</h2>
		<!-- The weekday is a label beside the date rather than a word inside
		     it — see `day.ts`. Today says so instead: that is the more useful
		     thing to know about it, and you already know what day today is. -->
		<span
			class="text-[10px] font-bold tracking-[0.22em] uppercase {today
				? 'text-accent-700'
				: 'text-neutral-600'}"
		>
			{today ? 'Today' : weekdayLabel(page.day.key)}
		</span>
		{#if page.parts > 1}
			<!-- A heavy day continues, and says so where the date is rather than
			     at the foot: you can land on part three from a jump, and a page
			     that does not say which part it is reads as the day starting
			     over. -->
			<span class="font-mono text-[12px] text-neutral-600 tabular-nums">
				{page.part + 1}/{page.parts}
			</span>
		{/if}
		<span class="ml-auto flex items-center gap-3 text-[12px] text-neutral-700 tabular-nums">
			<span class="flex items-center gap-1.5">
				<Glyph kind="entries" count={page.day.entries.length} size={12} />
				{page.day.entries.length}
			</span>
			{#if page.shots.length}
				<span class="flex items-center gap-1.5">
					<Glyph kind="media" count={page.shots.length} size={12} />
					{page.shots.length}
				</span>
			{/if}
		</span>
	</div>

	{#if shown.length}
		<div class="grid gap-[9px]" style="grid-template-columns:repeat({across}, minmax(0, 1fr))">
			{#each shown as shot, i (shot.entry.id + ':' + shot.ref)}
				{@const more = hidden > 0 && i === shown.length - 1}
				<button
					type="button"
					class="lift {across === 1 ? 'lift-md shadow-lg' : 'lift-sm shadow-sm'} relative block w-full overflow-hidden bg-neutral-300
					       {across === 1 ? 'h-[300px]' : across === 2 ? 'h-[220px]' : 'h-[170px]'}"
					use:hold={(x, y) => onholdmedia?.(shot.ref, x, y)}
					onclick={() => onopen?.(page.shots, i)}
					aria-label={more ? `${hidden + 1} more` : isVideo(shot.ref) ? 'play clip' : 'open photo'}
				>
					<img
						src={mediaViewUrl(shot.ref)}
						alt=""
						loading={i === 0 ? undefined : 'lazy'}
						decoding="async"
						onerror={(e) => plateFallback(e, shot.ref)}
						class="h-full w-full object-cover"
					/>
					{#if more}
						<span
							class="absolute inset-0 flex items-center justify-center bg-ground/70 text-[17px] font-semibold text-ink"
						>
							+{hidden + 1}
						</span>
					{:else if isVideo(shot.ref)}
						<!-- Never a `<video>` in a tile: a day with thirty clips would
						     be thirty media pipelines. The poster and a badge. -->
						<span
							class="absolute bottom-1.5 left-1.5 bg-ground/85 px-[5px] py-[2px] font-mono text-[9px] text-neutral-800"
						>
							▶
						</span>
					{/if}
				</button>
			{/each}
		</div>
	{/if}

	{#if page.caption && page.caption.clean_text.trim()}
		{@const caption = page.caption}
		<!-- What was said about the first photograph, larger than the lines
		     under it — and in the same gutter they are, with its time. -->
		<div
			data-entry={caption.id}
			class="flex gap-5"
			class:entry-held={caption.id === held}
			use:hold={(x, y) => onassign?.(caption, x, y)}
		>
			<span class="w-[42px] shrink-0 pt-[7px] font-mono text-[11px] text-neutral-600">
				{time(caption)}
			</span>
			<p
				class="max-w-[640px] min-w-0 text-[19px] leading-[1.5] font-light tracking-[-0.01em]"
				style="text-wrap:pretty"
			>
				<ColorizedText text={caption.clean_text} />
			</p>
		</div>
	{/if}

	{#if page.lines.length}
		<div class="flex max-w-[700px] flex-col gap-3.5 pt-1">
			{#each page.lines as entry (entry.id)}
				<!-- Right-click, or long-press on a phone: file this line into a
				     folder without having tagged it. -->
				{@const answered = !!entry.reply_to}
				{@const answeredBy = !entry.reply_to && !!entry.replied_by}
				<div
					data-entry={entry.id}
					class="flex gap-5"
					class:entry-held={entry.id === held}
					use:hold={(x, y) => onassign?.(entry, x, y)}
				>
					<span class="w-[42px] shrink-0 pt-1 font-mono text-[11px] text-neutral-600">
						{time(entry)}
					</span>
					{#if entry.todo_lines.length > 0}
						<TodoEntryText {entry} ontoggle={(line) => ontoggle?.(entry, line)} />
					{:else if answered}
						<div class="min-w-0 text-[17px] leading-[1.55] font-light">
							<ReplyBubble {entry} {onjump} {onopen} />
						</div>
					{:else if answeredBy}
						<button
							type="button"
							class="group/answered min-w-0 text-left text-[17px] leading-[1.55] font-light text-neutral-700 transition-colors hover:text-neutral-800"
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
						<p class="min-w-0 text-[17px] leading-[1.55] font-light" style="overflow-wrap:anywhere">
							<ColorizedText text={entry.clean_text} />
						</p>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</article>
