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
	 * On the editor: the source's markdown editor (Milkdown Crepe) went with the
	 * notes system this app removed, so there is no rich text to reuse. This is a
	 * plain field in the app's own type, which is also the honest match for what
	 * an overview is — a paragraph or two, not a document.
	 */
	import { mediaViewUrl, mediaUrl } from './api';
	import type { Folder } from './api';

	let {
		folder,
		expanded = $bindable(false),
		onsave,
		onclearmedia
	}: {
		folder: Folder;
		expanded?: boolean;
		onsave: (text: string) => void;
		onclearmedia?: () => void;
	} = $props();

	let editing = $state(false);
	let draft = $state('');

	const text = $derived(folder.overview ?? '');
	const picture = $derived(folder.overview_media ?? '');
	/** Written, or given a picture — either makes the overview a thing that
	 *  exists. `exists` is what turns the call to action into a title. */
	const exists = $derived(text.length > 0 || picture.length > 0);
	/** A picture and no words: the state the `!` is for. */
	const unwritten = $derived(picture.length > 0 && text.length === 0);

	const label = $derived(exists ? `Overview of ${folder.name}` : 'Create Overview');

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
		editing = false;
		if (draft !== text) onsave(draft);
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
		<div class="mt-[18px] flex min-h-0 flex-1 gap-[22px] overflow-y-auto pb-10">
			<div class="shrink-0">
				{#if picture}
					<a
						href={mediaUrl(picture)}
						target="_blank"
						rel="noreferrer"
						class="block h-[132px] w-[132px] overflow-hidden rounded-[14px] bg-neutral-200 shadow-md"
					>
						<img src={mediaViewUrl(picture)} alt="" class="h-full w-full object-cover" />
					</a>
					{#if onclearmedia && !editing}
						<button
							type="button"
							class="mt-2 text-[11px] text-neutral-700 transition-colors hover:text-ink"
							onclick={onclearmedia}
						>
							remove picture
						</button>
					{/if}
				{:else}
					<!-- The placeholder says how to fill it, because there is no
					     control here that does: the picture is set by holding one in
					     the log or the contact sheet. -->
					<div
						class="flex h-[132px] w-[132px] flex-col items-center justify-center gap-1.5 rounded-[14px] border-[1.5px] border-dashed border-neutral-400 px-3 text-center"
					>
						<span class="text-[18px] text-neutral-600">▢</span>
						<span class="text-[10px] leading-[1.35] text-neutral-700">
							hold a photograph to set one
						</span>
					</div>
				{/if}
			</div>

			<div class="min-w-0 flex-1">
				{#if editing}
					<!-- svelte-ignore a11y_autofocus -->
					<textarea
						autofocus
						bind:value={draft}
						placeholder="What is this project, and what is it for?"
						aria-label="overview"
						class="h-full min-h-[220px] w-full resize-none rounded-[14px] bg-surface p-4 text-[14px] leading-[1.6] shadow-md placeholder:text-neutral-700"
					></textarea>
				{:else if text}
					<p class="text-[14px] leading-[1.7] whitespace-pre-wrap">{text}</p>
				{:else}
					<p class="text-[13px] text-neutral-700">
						Nothing written yet. Edit to describe what this is.
					</p>
				{/if}
			</div>
		</div>
	{/if}
</div>
