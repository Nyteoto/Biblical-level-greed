<script lang="ts">
	/**
	 * One day of the journal: what you made, then what you said about it.
	 *
	 * This is the unit the Log is built from, and the shape is the argument.
	 * The ruler it replaces showed one day at a time through a 520px slot,
	 * which answers "what did I write" and cannot answer "how much is in
	 * here". A day is a header, a contact sheet, and a list of lines — the
	 * media first because that is where the density is, the text after because
	 * a day with no photographs should collapse to a clean list rather than a
	 * wall of empty cards.
	 *
	 * The header is sticky. Scrolling a long day, the thing you lose first is
	 * which day you are in, and it is the one label that cannot be re-derived
	 * from what is on screen.
	 *
	 * Media is pooled across the day rather than kept with its entry. Three
	 * clips written into three lines within a minute are one moment, and
	 * putting them in one grid says so; the line each came from is still one
	 * tap away in the lightbox.
	 */
	import EntryRow from './EntryRow.svelte';
	import MediaTile from './MediaTile.svelte';
	import { longpress } from './longpress';
	import type { Shot } from './media';
	import type { Entry, Folder } from './api';

	let {
		day,
		label,
		entries,
		foldersOf,
		onopen,
		ontoggle,
		onassign
	}: {
		day: string;
		label: string;
		entries: Entry[];
		/** Which folders an entry resolves into. Membership is a query, never a
		 *  stored fact, so the page that knows the mapping supplies this. */
		foldersOf?: (entry: Entry) => Folder[];
		onopen?: (shots: Shot[], index: number) => void;
		ontoggle?: (entry: Entry, line: number) => void;
		onassign?: (entry: Entry, x: number, y: number) => void;
	} = $props();

	const shots = $derived(
		entries.flatMap((entry) => (entry.media ?? []).map((ref) => ({ ref, entry })))
	);

	/** A line with no words is a line whose whole content is in the grid. */
	const lines = $derived(entries.filter((entry) => entry.clean_text.trim().length > 0));

	/** The folder colours touched today, deduplicated, in the order met. */
	const dots = $derived.by(() => {
		if (!foldersOf) return [];
		const seen = new Map<string, Folder>();
		for (const entry of entries) {
			for (const folder of foldersOf(entry)) if (!seen.has(folder.id)) seen.set(folder.id, folder);
		}
		return [...seen.values()];
	});

	const tally = $derived(
		[
			`${entries.length} ${entries.length === 1 ? 'capture' : 'captures'}`,
			shots.length ? `${shots.length} media` : ''
		]
			.filter(Boolean)
			.join(' · ')
	);
</script>

<section data-day={day} class="flex flex-col gap-3">
	<header
		class="sticky top-0 z-20 -mx-6 flex items-baseline gap-3 bg-[#14100c] px-6 py-2.5 text-[11px]"
	>
		<span class="shrink-0 text-stone-300">{label}</span>
		{#if dots.length}
			<span class="flex shrink-0 items-center gap-1">
				{#each dots as folder (folder.id)}
					<span
						class="h-1.5 w-1.5 rounded-full"
						style="background:{folder.color}"
						title={folder.name}
					></span>
				{/each}
			</span>
		{/if}
		<!-- A rule that eats whatever space is left, so the tally sits hard
		     right whatever the label's length. -->
		<span class="h-px min-w-4 flex-1 bg-stone-800/70"></span>
		<span class="shrink-0 text-stone-600 tabular-nums">{tally}</span>
	</header>

	{#if shots.length}
		<div class="grid grid-cols-3 gap-1 sm:grid-cols-5">
			{#each shots as shot, i (shot.entry.id + ':' + shot.ref)}
				<MediaTile ref={shot.ref} onopen={() => onopen?.(shots, i)} />
			{/each}
		</div>
	{/if}

	{#if lines.length}
		<div class="flex flex-col gap-1 pb-2">
			{#each lines as entry, i (entry.id)}
				<!-- Right-click, or long-press on a phone: file this line into a
				     folder without having tagged it. -->
				<div class="py-0.5" use:longpress={(x, y) => onassign?.(entry, x, y)}>
					<EntryRow
						{entry}
						index={i}
						media={false}
						ontoggle={(line) => ontoggle?.(entry, line)}
					/>
				</div>
			{/each}
		</div>
	{/if}
</section>
