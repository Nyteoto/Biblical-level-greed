<script lang="ts">
	/**
	 * The folder's overview: what this project is, and one picture for it.
	 *
	 * It sits above the day view and is the only thing in the app that is *about*
	 * a folder rather than written into it. Everything else on this screen is a
	 * fold over captures; this is a standing description you maintain, which is
	 * why it is stored as its own event (`set-overview`) and not inferred from
	 * anything.
	 *
	 * ## Three states, and why the collapsed one carries the weight
	 *
	 * Collapsed, it is a single bar, and the bar's label is the whole status:
	 *
	 *   - **`Create Overview`** — never written, no picture. A call to action,
	 *     because an empty card that says "Overview" is a thing you have to open
	 *     to discover is empty.
	 *   - **`Overview of Garden`** — written. It names the folder because this
	 *     card can be the only thing on screen once it is open, and a heading
	 *     that says only "Overview" loses track of what it is an overview of.
	 *   - **`Overview of Garden  !`** — a picture was set before any words were.
	 *     Setting the picture creates the overview, so the card exists and is
	 *     empty, and the `!` is the only way that state announces itself. No
	 *     blinking: it is a note, not an alarm.
	 *
	 * Open, it **takes the day view's place** rather than pushing it down. An
	 * overview can be as long as the project it describes, and a card that grows
	 * downward turns the reading column into a thing you scroll past to reach the
	 * days. The page is what performs that swap — this component only says
	 * whether it is open — because the day column is the page's to hide.
	 *
	 * The edit button is only there when the card is open, which follows from the
	 * same idea: collapsed, this is a label and a way in, and a second control on
	 * it would make a one-line bar into a toolbar.
	 *
	 * The picture does not get a column of its own. A 132px square beside a full
	 * width of prose left most of that column empty and pushed the text into a
	 * narrow strip; it floats now, and the writing runs around it the way a
	 * plate does on a page. It is the folder's face, not a panel.
	 *
	 * The editor is `RichText` — see it for why this app grew one rather than
	 * bringing back Milkdown, which left with the notes system.
	 */
	import { mediaViewUrl, mediaUrl } from './api';
	import RichText from './RichText.svelte';
	import { clean, isBlank } from './richtext';
	import { hold } from './hold';
	import Glyph from './Glyph.svelte';
	import { duration } from './timer';
	import type { Folder } from './api';

	let {
		folder,
		expanded = $bindable(false),
		onsave,
		onholdpicture,
		year = null,
		group = '',
		entries = 0,
		media = 0,
		seconds = 0,
		todos = { made: 0, done: 0 },
		sentiments = []
	}: {
		folder: Folder;
		expanded?: boolean;
		onsave: (text: string) => void;
		/** Hold the picture for what can be done to it. There is no button for
		 *  removing it: a control that sits on screen forever to be used twice is
		 *  the noise the hold gesture exists to delete. */
		onholdpicture?: (x: number, y: number) => void;
		/** The album's facts — this folder seen through the year on screen.
		 *  Passed in rather than fetched: this card is a child of the page that
		 *  already has them, and a second request for the same numbers would be
		 *  able to disagree with the ones beside it. */
		year?: string | null;
		group?: string;
		entries?: number;
		media?: number;
		/** Seconds clocked into this album this year. Passed in with the rest of
		 *  the album's facts, for the same reason they are. */
		seconds?: number;
		/** Promises made in here and promises kept. A fact about the folder in
		 *  the same way the entry count is, which is why it sits in the row of
		 *  figures and not under the readings — a reading is drawn and never
		 *  interpreted, and this one is arithmetic with an answer. */
		todos?: { made: number; done: number };
		sentiments?: { name: string; count: number }[];
	} = $props();

	let editing = $state(false);
	let draft = $state('');
	/** The live field, so `save()` can read what is in it rather than what the
	 *  binding last managed to deliver. */
	let field = $state<{ current: () => string } | null>(null);

	const text = $derived(folder.overview ?? '');
	const picture = $derived(folder.overview_media ?? '');
	/** An editor left empty still reports `<br>`, so emptiness is measured by
	 *  what a reader would see rather than by string length. */
	const written = $derived(!isBlank(text));
	/** Written, or given a picture — either makes the overview a thing that
	 *  exists. `exists` is what turns the call to action into a title. */
	const exists = $derived(written || picture.length > 0);
	/** A picture and no words: the state the `!` is for. */
	const unwritten = $derived(picture.length > 0 && !written);

	const label = $derived(exists ? `Overview of ${folder.name}` : 'Create Overview');

	/** The day the folder was made, in the reader's own locale. Long-form on
	 *  purpose: this is read once in a while, not scanned in a column. */
	const created = $derived(
		folder.created_ts
			? new Date(folder.created_ts).toLocaleDateString(undefined, {
					year: 'numeric',
					month: 'long',
					day: 'numeric'
				})
			: ''
	);
	const peak = $derived(Math.max(...sentiments.map((s) => s.count), 1));

	function open() {
		expanded = true;
		// Straight into the editor the first time: the call to action promised
		// creating one, and opening an empty card to then press edit is the same
		// two taps with a blank screen in the middle.
		if (!exists) startEditing();
	}

	function startEditing() {
		draft = text;
		editing = true;
	}

	function save() {
		// Read the element before tearing the editor down: `editing = false`
		// unmounts it, and `field` with it.
		const typed = field?.current() ?? draft;
		editing = false;
		const kept = isBlank(typed) ? '' : clean(typed);
		// No "did it change" guard. It cost nothing to write the same string
		// again, and the guard is what turned a save that failed to see your
		// keystrokes into a card that quietly went passive with nothing kept.
		onsave(kept);
	}
</script>

<div class="flex flex-col">
	<!-- The bar. Present in every state, so the card never disappears on you —
	     it is the folder's own row, and the day view starts underneath it. -->
	<div class="flex items-center gap-3">
		<button
			type="button"
			class="lift lift-sm flex min-w-0 flex-1 items-center gap-2.5 rounded-[12px] bg-surface px-4 py-[11px] text-left shadow-sm"
			aria-expanded={expanded}
			onclick={() => (expanded ? (expanded = false) : open())}
		>
			<span class="shrink-0 text-[13px] text-neutral-600">{expanded ? '▾' : '▸'}</span>
			<span class="min-w-0 flex-1 truncate text-[14px] font-semibold {exists ? '' : 'text-accent-700'}">
				{label}
			</span>
			{#if unwritten}
				<!-- Said in the button rather than beside it: the state belongs to
				     the overview, not to the screen. -->
				<span class="shrink-0 text-[14px] font-bold text-accent-700" title="no words yet">!</span>
			{/if}
		</button>

		{#if expanded && !editing}
			<button
				type="button"
				class="lift lift-sm shrink-0 rounded-[12px] bg-surface px-4 py-[11px] text-[13px] font-semibold shadow-sm"
				onclick={startEditing}
			>
				Edit
			</button>
		{/if}
		{#if editing}
			<button
				type="button"
				class="accent-fill shrink-0 rounded-[12px] px-4 py-[11px] text-[13px] font-semibold"
				onclick={save}
			>
				Save
			</button>
		{/if}
	</div>

	{#if expanded}
		<!-- The body. `min-h-0` and its own scroll, because this is standing in
		     for the day column and inherits the column's job of being the one
		     thing on the screen that scrolls. -->
		<div class="mt-[18px] flex min-h-0 flex-1 flex-col overflow-y-auto pb-10">
			{#if editing}
				<RichText
					bind:this={field}
					bind:html={draft}
					placeholder="What is this project, and what is it for?"
				/>
			{:else}
				<div class="min-h-0 flex-1">
					{#if picture}
						<!-- Floated, so the prose closes around it instead of starting
						     after it. `shape-outside` is not worth it on a square. -->
						<a
							href={mediaUrl(picture)}
							target="_blank"
							rel="noreferrer"
							use:hold={(x, y) => onholdpicture?.(x, y)}
							class="float-left mr-[18px] mb-3 block h-[104px] w-[104px] overflow-hidden rounded-[14px] bg-neutral-200 shadow-md"
						>
							<img src={mediaViewUrl(picture)} alt="" class="h-full w-full object-cover" />
						</a>
					{:else}
						<div
							class="float-left mr-[18px] mb-3 flex h-[104px] w-[104px] flex-col items-center justify-center gap-1 rounded-[14px] border-[1.5px] border-dashed border-neutral-400 px-2 text-center"
						>
							<span class="text-[16px] text-neutral-600">▢</span>
							<span class="text-[10px] leading-[1.3] text-neutral-700">hold a photograph</span>
						</div>
					{/if}

					{#if written}
						<div class="prose-overview text-[14px] leading-[1.7]">
							<!-- eslint-disable-next-line svelte/no-at-html-tags -->
							{@html text}
						</div>
					{:else}
						<p class="text-[13px] text-neutral-700">
							Nothing written yet. Edit to describe what this is.
						</p>
					{/if}

					<div class="clear-both"></div>

					<!-- The folder's own facts. Below the prose rather than beside
					     it: the description is what you came to read, and a column
					     of figures next to it would compete with the writing for
					     the eye every time the card opened. -->
					<dl
						class="mt-7 flex flex-wrap items-baseline gap-x-9 gap-y-3 border-t border-neutral-300 pt-5 text-[12px]"
					>
						{#if year}
							<div class="flex flex-col gap-1">
								<dt class="text-[10px] font-bold tracking-[0.16em] text-neutral-600 uppercase">
									Group {year}
								</dt>
								<dd class={group ? '' : 'text-neutral-700'}>{group || 'none'}</dd>
							</div>
						{/if}
						<div class="flex flex-col gap-1">
							<dt class="text-[10px] font-bold tracking-[0.16em] text-neutral-600 uppercase">
								Created
							</dt>
							<dd>{created || '—'}</dd>
						</div>
						<div class="flex flex-col gap-1">
							<dt class="text-[10px] font-bold tracking-[0.16em] text-neutral-600 uppercase">
								Entries
							</dt>
							<dd class="flex items-center gap-1.5 tabular-nums">
								<Glyph kind="entries" count={entries} size={12} />
								{entries.toLocaleString()}
							</dd>
						</div>
						<div class="flex flex-col gap-1">
							<dt class="text-[10px] font-bold tracking-[0.16em] text-neutral-600 uppercase">
								Media
							</dt>
							<dd class="flex items-center gap-1.5 tabular-nums">
								<Glyph kind="media" count={media} size={12} />
								{media.toLocaleString()}
							</dd>
						</div>
						{#if seconds > 0}
							<!-- Only when there is time on it, like the todos below. A
							     project with no clock on it is not a project with a zero;
							     it is one you have not timed, and those are different. -->
							<div class="flex flex-col gap-1">
								<dt class="text-[10px] font-bold tracking-[0.16em] text-neutral-600 uppercase">
									Clocked
								</dt>
								<dd class="flex items-center gap-1.5 tabular-nums">
									<Glyph kind="time" size={12} />
									{duration(seconds)}
								</dd>
							</div>
						{/if}
						{#if todos.made > 0}
							<!-- Kept over made, in that order, because it is the same pair
							     the capture screen stands a badge on — a ratio that swapped
							     ends between two screens would be read wrong on one of
							     them. Only when there are any: a folder nobody promised
							     anything in has no ratio, and `0/0` looks like a fault. -->
							<div class="flex flex-col gap-1">
								<dt class="text-[10px] font-bold tracking-[0.16em] text-neutral-600 uppercase">
									Todos
								</dt>
								<dd
									class="flex items-center gap-1.5 tabular-nums"
									title="{todos.done} of {todos.made} kept"
								>
									<Glyph kind="todo" count={todos.made} size={12} />
									<span>
										{todos.done.toLocaleString()}<span class="text-neutral-600">/</span
										>{todos.made.toLocaleString()}
									</span>
								</dd>
							</div>
						{/if}
						{#if folder.tags.length > 0}
							<div class="flex min-w-0 flex-col gap-1">
								<dt class="text-[10px] font-bold tracking-[0.16em] text-neutral-600 uppercase">
									Tags
								</dt>
								<dd class="flex flex-wrap gap-x-2.5 gap-y-1 font-mono">
									{#each folder.tags as tag (tag)}
										<span style="color:var(--color-accent-700)">{`<${tag}>`}</span>
									{/each}
								</dd>
							</div>
						{/if}
					</dl>

					{#if sentiments.length > 0}
						<!-- The `\pattern` counts. Stored and drawn, never interpreted
						     — a reading, not a verdict, which is why there is no
						     sentence under them saying what they mean. -->
						<div class="mt-6 flex max-w-[440px] flex-col gap-2">
							<div class="text-[10px] font-bold tracking-[0.16em] text-neutral-600 uppercase">
								Readings
							</div>
							{#each sentiments as s (s.name)}
								<div class="flex items-center gap-3 text-[12px]">
									<span
										class="w-24 shrink-0 truncate text-right font-mono"
										style="color:var(--color-accent-700)"
									>
										{`\\${s.name}`}
									</span>
									<div class="h-[7px] flex-1 overflow-hidden rounded-[4px] bg-neutral-200">
										<div
											class="h-full rounded-[4px]"
											style="width:{(s.count / peak) * 100}%;background:var(--gradient-accent)"
										></div>
									</div>
									<span class="w-8 shrink-0 text-right tabular-nums text-neutral-700">
										{s.count}
									</span>
								</div>
							{/each}
						</div>
					{/if}
				</div>
			{/if}
		</div>
	{/if}
</div>
