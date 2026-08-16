<script lang="ts">
	/**
	 * The newest day of an album, given the whole treatment: the photograph
	 * first, then what was said about it, then the ribbon of everything else
	 * made that day, then the remaining lines with their times.
	 *
	 * The order is the argument. The ruler this replaced put the words first
	 * and the media in a footnote, which is backwards for a journal whose
	 * entries are mostly photographs and clips — the picture is what you
	 * recognise the day by, and the caption is what you wrote about it.
	 *
	 * **The lead photograph is the newest attachment, and the caption is the
	 * line it was written beside** — not a separate field. There is nowhere to
	 * write a caption in this app; a caption is a capture that happened to
	 * carry a photograph, which is why one line is promoted out of the list
	 * rather than duplicated in it.
	 *
	 * Media is pooled across the whole day rather than kept with its entry.
	 * Three clips written into three lines within a minute are one moment, and
	 * one ribbon says so; the line each came from is still one tap away in the
	 * lightbox.
	 */
	import ColorizedText from './ColorizedText.svelte';
	import TodoEntryText from './TodoEntryText.svelte';
	import { longpress } from './longpress';
	import { mediaUrl, mediaViewUrl } from './api';
	import { isVideo, type Shot } from './media';
	import { dayLabel } from './log';
	import type { Day } from './log';
	import type { Entry } from './api';

	let {
		day,
		today = false,
		onopen,
		ontoggle,
		onassign
	}: {
		day: Day;
		today?: boolean;
		onopen?: (shots: Shot[], index: number) => void;
		ontoggle?: (entry: Entry, line: number) => void;
		onassign?: (entry: Entry, x: number, y: number) => void;
	} = $props();

	/** How many thumbnails fit before the overflow tile earns its place. */
	const RIBBON = 5;

	const shots = $derived(day.media);
	const hero = $derived(shots[0] ?? null);
	/** The line the lead photograph was written beside, promoted out of the
	 *  list below so it is not said twice. */
	const caption = $derived(hero?.entry ?? null);
	const rest = $derived(day.lines.filter((entry) => entry.id !== caption?.id));
	const ribbon = $derived(shots.slice(1));

	const time = (entry: Entry) =>
		new Date(entry.ts).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });

	function onViewMissing(event: Event, ref: string) {
		const el = event.currentTarget as HTMLImageElement;
		if (el.src.endsWith('.view.jpg') && !isVideo(ref)) el.src = mediaUrl(ref);
	}

	const tally = $derived(
		[
			`${day.entries.length} ${day.entries.length === 1 ? 'capture' : 'captures'}`,
			shots.length ? `${shots.length} media` : ''
		]
			.filter(Boolean)
			.join(' · ')
	);
</script>

<article data-day={day.key} class="flex flex-col gap-[18px]">
	<div class="flex items-baseline gap-3.5">
		{#if today}
			<span class="text-[10px] font-bold tracking-[0.2em] text-accent-700 uppercase">Today</span>
		{/if}
		<h2 class="text-[34px] leading-none font-extrabold tracking-[-0.03em]">
			{dayLabel(day.key)}
		</h2>
		<span class="ml-auto text-[12px] text-neutral-700 tabular-nums">{tally}</span>
	</div>

	{#if hero}
		<button
			type="button"
			class="lift lift-md relative block h-[250px] w-full overflow-hidden rounded-[16px] bg-neutral-300 shadow-lg"
			style="animation:plate-fade-in 400ms ease-out both"
			onclick={() => onopen?.(shots, 0)}
			aria-label="open the newest"
		>
			<img
				src={mediaViewUrl(hero.ref)}
				alt=""
				onerror={(e) => onViewMissing(e, hero.ref)}
				class="h-full w-full object-cover"
			/>
			<!-- The file's own name, in the mono. It is the one thing about a
			     photograph the app knows and did not invent. -->
			<span
				class="absolute bottom-4 left-4 rounded-[7px] bg-white/[0.88] px-2 py-1 font-mono text-[11px] text-neutral-800"
			>
				{hero.ref.split('/').pop()}
			</span>
		</button>
	{/if}

	{#if caption && caption.clean_text.trim()}
		<div use:longpress={(x, y) => onassign?.(caption, x, y)}>
			<p
				class="max-w-[640px] text-[19px] leading-[1.5] tracking-[-0.01em]"
				style="text-wrap:pretty"
			>
				<ColorizedText text={caption.clean_text} />
			</p>
		</div>
	{/if}

	{#if ribbon.length}
		<div class="trophic-scrollbar-hide flex items-center gap-[9px] overflow-x-auto">
			{#each ribbon.slice(0, RIBBON) as shot, i (shot.entry.id + ':' + shot.ref)}
				<button
					type="button"
					class="lift lift-sm relative h-[70px] w-[96px] shrink-0 overflow-hidden rounded-[11px] bg-neutral-300 shadow-sm"
					onclick={() => onopen?.(shots, i + 1)}
					aria-label={isVideo(shot.ref) ? 'play clip' : 'open photo'}
				>
					<img
						src={mediaViewUrl(shot.ref)}
						alt=""
						loading="lazy"
						decoding="async"
						onerror={(e) => onViewMissing(e, shot.ref)}
						class="h-full w-full object-cover"
					/>
					{#if isVideo(shot.ref)}
						<!-- Never a `<video>` in a tile: a day with thirty clips would
						     be thirty media pipelines. The poster and a badge. -->
						<span
							class="absolute bottom-1.5 left-1.5 rounded-[5px] bg-white/[0.88] px-[5px] py-[2px] font-mono text-[9px] text-neutral-800"
						>
							▶
						</span>
					{/if}
				</button>
			{/each}
			{#if ribbon.length > RIBBON}
				<button
					type="button"
					class="lift lift-sm flex h-[70px] w-[96px] shrink-0 items-center justify-center rounded-[11px] bg-surface text-[13px] text-neutral-700 shadow-sm"
					onclick={() => onopen?.(shots, RIBBON + 1)}
				>
					+{ribbon.length - RIBBON}
				</button>
			{/if}
		</div>
	{/if}

	{#if rest.length}
		<div class="flex max-w-[700px] flex-col gap-3.5 pt-1">
			{#each rest as entry, i (entry.id)}
				<!-- Right-click, or long-press on a phone: file this line into a
				     folder without having tagged it. -->
				<div
					class="flex gap-5"
					style="animation:entry-fade-in 400ms ease-out both;animation-delay:{i * 50}ms"
					use:longpress={(x, y) => onassign?.(entry, x, y)}
				>
					<span class="w-[42px] shrink-0 pt-1 font-mono text-[11px] text-neutral-700">
						{time(entry)}
					</span>
					{#if entry.todo_lines.length > 0}
						<TodoEntryText {entry} ontoggle={(line) => ontoggle?.(entry, line)} />
					{:else}
						<p class="min-w-0 text-[17px] leading-[1.55]" style="overflow-wrap:anywhere">
							<ColorizedText text={entry.clean_text} />
						</p>
					{/if}
				</div>
			{/each}
		</div>
	{/if}
</article>
