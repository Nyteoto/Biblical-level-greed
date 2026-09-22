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
	 * photograph first, then what was said about it, then the ribbon of
	 * everything else made that day, then the remaining lines with their times.
	 * You recognise a day by the picture and read the words once you have found
	 * it.
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

	/** How many thumbnails fit before the overflow tile earns its place. */
	const RIBBON = 5;

	const time = (entry: Entry) =>
		new Date(entry.ts).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
</script>

<article
	data-day={page.day.key}
	data-page={page.key}
	class="flex flex-col gap-[18px] px-4 py-5 sm:px-[30px] sm:py-[26px]"
>
	<div class="flex items-baseline gap-3.5">
		{#if today}
			<span class="text-[10px] font-bold tracking-[0.22em] text-accent-700 uppercase">Today</span>
		{/if}
		<h2 class="text-[34px] leading-none font-extrabold tracking-[-0.03em]">
			{dayLabel(page.day.key)}
		</h2>
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

	{#if page.hero}
		{@const hero = page.hero}
		<button
			type="button"
			class="lift lift-md relative block h-[250px] w-full overflow-hidden rounded-[16px] bg-neutral-300 shadow-lg"
			use:hold={(x, y) => onholdmedia?.(hero.ref, x, y)}
			onclick={() => onopen?.(page.shots, 0)}
			aria-label="open the newest"
		>
			<img
				src={mediaViewUrl(hero.ref)}
				alt=""
				onerror={(e) => plateFallback(e, hero.ref)}
				class="h-full w-full object-cover"
			/>
			<!-- The file's own name, in the mono. It is the one thing about a
			     photograph the app knows and did not invent. -->
			<span
				class="absolute bottom-4 left-4 rounded-[7px] bg-ground/85 px-2 py-1 font-mono text-[11px] text-neutral-800"
			>
				{hero.ref.split('/').pop()}
			</span>
		</button>
	{/if}

	{#if page.caption && page.caption.clean_text.trim()}
		{@const caption = page.caption}
		<div use:hold={(x, y) => onassign?.(caption, x, y)}>
			<p
				class="max-w-[640px] text-[19px] leading-[1.5] font-light tracking-[-0.01em]"
				style="text-wrap:pretty"
			>
				<ColorizedText text={caption.clean_text} />
			</p>
		</div>
	{/if}

	{#if page.ribbon.length}
		<div class="trophic-scrollbar-hide flex items-center gap-[9px] overflow-x-auto">
			{#each page.ribbon.slice(0, RIBBON) as shot, i (shot.entry.id + ':' + shot.ref)}
				<button
					type="button"
					class="lift lift-sm relative h-[70px] w-[96px] shrink-0 overflow-hidden rounded-[11px] bg-neutral-300 shadow-sm"
					use:hold={(x, y) => onholdmedia?.(shot.ref, x, y)}
					onclick={() => onopen?.(page.shots, i + 1)}
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
						<!-- Never a `<video>` in a tile: a day with thirty clips would
						     be thirty media pipelines. The poster and a badge. -->
						<span
							class="absolute bottom-1.5 left-1.5 rounded-[5px] bg-ground/85 px-[5px] py-[2px] font-mono text-[9px] text-neutral-800"
						>
							▶
						</span>
					{/if}
				</button>
			{/each}
			{#if page.ribbon.length > RIBBON}
				<button
					type="button"
					class="lift lift-sm flex h-[70px] w-[96px] shrink-0 items-center justify-center rounded-[11px] bg-neutral-200 text-[13px] text-neutral-700 shadow-sm"
					onclick={() => onopen?.(page.shots, RIBBON + 1)}
				>
					+{page.ribbon.length - RIBBON}
				</button>
			{/if}
		</div>
	{/if}

	{#if page.lines.length}
		<div class="flex max-w-[700px] flex-col gap-3.5 pt-1">
			{#each page.lines as entry (entry.id)}
				<!-- Right-click, or long-press on a phone: file this line into a
				     folder without having tagged it. -->
				{@const answered = !!entry.reply_to}
				{@const answeredBy = !entry.reply_to && !!entry.replied_by}
				<!-- A reply sits on the other side of the column: a thought you came
				     back to weeks later reads as a conversation with yourself, so the
				     answer is set against the margin the way a message you sent is. -->
				<div
					data-entry={entry.id}
					class="flex gap-5"
					class:flex-row-reverse={answered}
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
