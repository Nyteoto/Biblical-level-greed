<script lang="ts">
	/**
	 * Record — the folder itself: what it is, and what points here.
	 *
	 * ## Its subject is the folder you are in, and nothing else
	 *
	 * This lens carried the folder *list* for two steps, because the list had to
	 * live somewhere and Map had just given it up. It was the third drawing of
	 * one list — Map's chips, this column, the old shelf's cards — and none of
	 * the three was reachable from the other lenses, which is how choosing a
	 * folder became a trip to Map before you could read one.
	 *
	 * The list is the shell's subject bar now, where the rail already is, and
	 * every power it had came with it: a hold opens `FolderPanel`, headings
	 * drag, `+ new folder` is still the only way to make one. What is left here
	 * is the folder you are *in* — its description, its figures, its chapters,
	 * its patterns, its clock, the tags that point at it, and the way to end it.
	 *
	 * ## What it will not do
	 *
	 * No year of days. That is Map's whole question and drawing it twice is
	 * exactly what the lenses exist to stop. The figures here are drawn and
	 * never interpreted: no target, no streak, no verdict.
	 */
	import { page } from '$app/state';
	import {
		deleteFolder,
		getAlbum,
		mediaUrl,
		mediaViewUrl,
		patchFolder,
		splitChapter,
		unsplitChapter,
		type AlbumView,
		type Chapter,
		type Folder
	} from '$lib/trophic/api';
	import { readScope } from '$lib/trophic/scope';
	import { lens } from '$lib/trophic/lens.svelte';
	import { subject } from '$lib/trophic/subject.svelte';
	import { clean, isBlank } from '$lib/trophic/richtext';
	import { MONTH_ABBR } from '$lib/trophic/log';
	import ChapterPanel from '$lib/trophic/ChapterPanel.svelte';
	import { duration } from '$lib/trophic/timer';
	import { hold } from '$lib/trophic/hold';
	import HoldMenu from '$lib/trophic/HoldMenu.svelte';
	import RichText from '$lib/trophic/RichText.svelte';
	import Segmented from '$lib/trophic/Segmented.svelte';

	const scope = $derived(readScope(page.url));
	const folderId = $derived(scope.folder === 'unfiled' ? null : scope.folder);

	const bar = subject();
	/** The loose tags, for the `Unclaimed` row. The subject bar's, like the
	 *  shelf — this and the picker each fetched their own and neither
	 *  refetched, so a tag claimed here stayed on offer there. */
	const unassigned = $derived(bar.tags);
	/** A chapter's, from a press or a hold on one of its rows. Both, and not
	 *  only a hold: this is the screen chapters are *managed* on, so the panel
	 *  is the row's job rather than a gesture you have to know about — the
	 *  hold is what carries the same powers to the reading lens's index. */
	let chapterPanel = $state<{
		chapter: Chapter;
		x: number;
		y: number;
		/** True when a press opened it rather than a hold. The shell swallows
		 *  the first click after a hold — that is the release — and a
		 *  click-opened panel has no release to swallow. */
		armed: boolean;
	} | null>(null);
	/** Choosing where to cut. A month grid rather than a field, because the
	 *  twelve answers are all of them. */
	let cutting = $state(false);

	/** The dossier. No folder chosen is a real answer rather than a load —
	 *  Record's subject *is* the folder, so with none there is nothing to
	 *  draw and the screen says so. */
	const view = lens(
		() => `${scope.folder ?? ''}:${scope.year}`,
		async () => (scope.folder ? await getAlbum(folderId, scope.year) : null),
		null as AlbumView | null
	);

	const album = $derived(view.data);
	const folder = $derived(view.data?.folder ?? null);

	/** Every edit re-reads the dossier, and the shelf with it — a rename
	 *  changes this screen and the name in the bar above it at once, and the
	 *  bar is the one place that list now lives. */
	async function act(work: Promise<unknown>) {
		chapterPanel = null;
		view.clear();
		try {
			await work;
		} catch (e) {
			view.fail(e);
		}
		await bar.refresh();
		await view.refresh();
	}

	function removeFolder(id: string) {
		// The folder, not what was written into it — the entries stay and their
		// tags go back in the unassigned pool.
		if (!confirm('Delete this folder? Its entries stay in the log.')) return;
		act(deleteFolder(id));
	}

	// ── The overview ──────────────────────────────────────────────────────
	//
	// The folder's standing description and its face. It stood at the top of
	// the reading lens until step 3, where it was the one thing on that screen
	// that was not a fold over captures — and it carried a row of figures this
	// dossier already prints. It is a description of the folder, so it belongs
	// on the lens whose subject is the folder.
	//
	// It is open rather than behind a collapsed bar. The bar existed because
	// the card was standing over the day view and had to get out of the way;
	// nothing is underneath it here, and a fold over three lines of prose is a
	// control that only ever hides the thing you came to read.
	//
	// **Choosing the picture stays on the Log**, where the photographs are: a
	// hold on one there sets it. What is here is seeing it and taking it off.
	let editing = $state(false);
	let draft = $state('');
	/** The live field, so `save()` reads what is in it rather than what the
	 *  binding last managed to deliver. */
	let field = $state<{ current: () => string } | null>(null);
	/** The picture, held. Its only option is removal, which is why it never had
	 *  a standing button. */
	let heldPicture = $state<{ x: number; y: number } | null>(null);

	const overview = $derived(folder?.overview ?? '');
	const picture = $derived(folder?.overview_media ?? '');
	/** An editor left empty still reports `<br>`, so emptiness is measured by
	 *  what a reader would see rather than by string length. */
	const written = $derived(!isBlank(overview));

	function startEditing() {
		draft = overview;
		editing = true;
	}

	function saveOverview() {
		// Read the element before tearing the editor down: `editing = false`
		// unmounts it, and `field` with it.
		const typed = field?.current() ?? draft;
		editing = false;
		const kept = isBlank(typed) ? '' : clean(typed);
		// No "did it change" guard. It costs nothing to write the same string
		// again, and the guard is what turned a save that failed to see your
		// keystrokes into a card that quietly went passive with nothing kept.
		act(patchFolder(folder!.id, { overview: kept }));
	}

	// A different folder is a different description: never carry a draft across.
	$effect(() => {
		void scope.folder;
		editing = false;
	});


	const STATES = [
		{ value: '', label: 'open' },
		{ value: 'active', label: 'running' },
		{ value: 'shipped', label: 'shipped' }
	];

	/** Every figure this folder can be described by that costs no new read.
	 *  Drawn and never interpreted — no target, no streak, no verdict. */
	const figures = $derived.by(() => {
		if (!album) return [];
		const counts = album.entries.length;
		return [
			{ n: String(counts), label: 'lines' },
			{ n: String(album.media_count), label: 'plates' },
			{ n: album.seconds ? duration(album.seconds) : '—', label: 'clocked' },
			{ n: String(new Set(album.entries.map((e) => e.day)).size), label: 'days' },
			{ n: String(album.chapters.length), label: 'chapters' },
			{ n: `${album.todos.done}/${album.todos.made}`, label: 'kept' }
		];
	});
</script>

<div class="flex min-h-0 flex-1">
	<!-- The folder list stood here and is the shell's subject bar now. It was
	     the third drawing of one list — Map's chips, this column, the old
	     shelf's cards — and none of the three was reachable from the other
	     lenses, which is how choosing a folder became a trip to Map. What is
	     left on this lens is the folder you are *in*, which is its subject.

	     Everything the column could do came with it: a hold on a row still
	     opens `FolderPanel`, headings still drag, `+ new folder` is still the
	     only way to make one. -->
	<!-- ═══ The dossier ═════════════════════════════════════════════════════ -->
	<main class="flex min-h-0 flex-1 flex-col overflow-y-auto px-8 pt-[22px] pb-10">
		{#if view.error}
			<p class="shrink-0 pb-3 text-[13px] text-error">{view.error}</p>
		{/if}

		{#if !scope.folder}
			<!-- No redirect. Record is where a folder is made, so landing here with
			     nothing chosen is a legitimate place to be — the list is the screen
			     at that point, and on a narrow window it is the whole screen. -->
			<p class="max-w-[56ch] text-[13px] leading-relaxed text-neutral-600">
				No folder chosen. Press the name at the top of the screen to pick one, or to make one.
			</p>
			{#if unassigned.length}
				<!-- Where Settings' "point them" row lands. The tags cannot be
				     pointed from here — a tag points *at* a folder — so this says
				     what is waiting and which press does it. -->
				<p class="mt-2 max-w-[56ch] text-[13px] leading-relaxed text-neutral-700">
					{unassigned.length}
					{unassigned.length === 1 ? 'tag points' : 'tags point'} nowhere. Open the folder they belong
					in and they are listed under Unclaimed.
				</p>
			{/if}
		{:else if view.loading && !album}
			<p class="text-[13px] text-neutral-600">Reading…</p>
		{:else if album}
			<div class="flex shrink-0 flex-wrap items-center gap-5">
				<h1 class="text-[34px] leading-none font-extrabold tracking-[-0.03em] text-neutral-800">
					{folder?.name ?? 'Unfiled'}
				</h1>
				{#if folder}
					<div class="ml-auto">
						<Segmented
							options={STATES}
							value={folder.state ?? ''}
							onpick={(state) => act(patchFolder(folder!.id, { state }))}
							label="this folder's state"
						/>
					</div>
				{/if}
			</div>

			{#if folder}
				<section class="mt-5 max-w-[68ch] shrink-0">
					{#if editing}
						<RichText
							bind:this={field}
							bind:html={draft}
							placeholder="What is this project, and what is it for?"
						/>
						<button
							type="button"
							class="accent-fill mt-3 h-11 px-4 text-[13px] font-semibold"
							onclick={saveOverview}
						>
							Save
						</button>
					{:else}
						<div class="text-[14px] leading-[1.7]">
							{#if picture}
								<!-- Floated, so the prose closes around it instead of
								     starting after it. `shape-outside` is not worth it on
								     a square. -->
								<a
									href={mediaUrl(picture)}
									target="_blank"
									rel="noreferrer"
									use:hold={(x, y) => (heldPicture = { x, y })}
									class="float-left mr-[18px] mb-3 block h-[104px] w-[104px] overflow-hidden bg-neutral-300"
									style="box-shadow:inset 0 0 0 1px var(--color-neutral-500)"
								>
									<img src={mediaViewUrl(picture)} alt="" class="h-full w-full object-cover" />
								</a>
							{:else}
								<div
									class="float-left mr-[18px] mb-3 flex h-[104px] w-[104px] flex-col items-center justify-center gap-1 px-2 text-center"
									style="box-shadow:inset 0 0 0 1px var(--color-neutral-400)"
								>
									<span class="text-[16px] text-neutral-600">▢</span>
									<!-- Where the gesture is, not what it is: choosing the
									     face means holding a photograph, and the Log is the
									     only lens that has any. -->
									<span class="text-[10px] leading-[1.3] text-neutral-700">
										hold a photo<br />on the Log
									</span>
								</div>
							{/if}

							{#if written}
								<!-- eslint-disable-next-line svelte/no-at-html-tags -->
								<div class="prose-overview">{@html overview}</div>
							{:else}
								<p class="text-[13px] text-neutral-600">
									Nothing written yet — what is this, and what is it for?
								</p>
							{/if}
						</div>
						<!-- The clear goes on a wrapper, not on the button: `clear`
						     applies to block boxes and a `<button>` is inline-level, so
						     the class on the button itself did nothing at all and it
						     tucked in beside the face instead of sitting under the
						     words it belongs to. -->
						<div class="clear-both pt-3">
							<button
								type="button"
								class="h-11 px-4 text-[13px] font-semibold text-neutral-800 transition-colors hover:text-ink"
								style="box-shadow:inset 0 0 0 1px var(--color-neutral-400)"
								onclick={startEditing}
							>
								{written ? 'Edit' : 'Describe it'}
							</button>
						</div>
					{/if}
				</section>
			{/if}

			<dl class="mt-9 grid shrink-0 grid-cols-2 gap-x-8 gap-y-6 sm:grid-cols-3 lg:grid-cols-6">
				{#each figures as f (f.label)}
					<div class="flex flex-col gap-2 pl-4" style="box-shadow:inset 1px 0 0 0 var(--color-neutral-400)">
						<!-- `nowrap`: `3h 10m` broke over two lines and took the whole
						     row's height with it, so five figures grew a line because
						     one of them is two words. -->
						<dd
							class="text-[28px] leading-none font-extrabold tracking-[-0.03em] whitespace-nowrap text-ink tabular-nums"
						>
							{f.n}
						</dd>
						<dt class="text-[10px] font-bold tracking-[0.16em] text-neutral-600 uppercase">
							{f.label}
						</dt>
					</div>
				{/each}
			</dl>

			<!-- ═══ Chapters ══════════════════════════════════════════════════
			     Cut by hand and never guessed. The list is the cuts in order,
			     newest first; a hold on one renames it or takes it back. -->
			<section class="mt-10 flex shrink-0 flex-col gap-3">
				<h2 class="text-[10px] font-bold tracking-[0.18em] text-neutral-600 uppercase">
					Chapters · {album.chapters.length}
				</h2>

				<div class="flex max-w-[68ch] flex-col">
					{#each album.chapters as chapter (chapter.month)}
						<button
							type="button"
							class="flex items-baseline gap-3 px-2 py-2.5 text-left transition-colors hover:bg-neutral-200"
							style="box-shadow:inset 2px 0 0 0 var(--color-neutral-500)"
							use:hold={(x, y) => (chapterPanel = { chapter, x, y, armed: false })}
							onclick={(e) =>
								(chapterPanel = { chapter, x: e.clientX, y: e.clientY, armed: true })}
						>
							<!-- A chapter with no name yet is drawn as its range, in the
							     grey. Nothing here invents a word for it. -->
							<span
								class="min-w-0 flex-1 truncate text-[15px] {chapter.name
									? 'font-semibold text-ink'
									: 'text-neutral-700'}"
							>
								{chapter.name || chapter.range}
							</span>
							{#if chapter.name}
								<span class="shrink-0 text-[12px] text-neutral-600">{chapter.range}</span>
							{/if}
							<span class="w-[70px] shrink-0 text-right text-[12px] text-neutral-600 tabular-nums">
								{chapter.entries}
								{chapter.entries === 1 ? 'line' : 'lines'}
							</span>
						</button>
					{:else}
						<p class="px-2 text-[13px] text-neutral-600">
							Nothing is chaptered. Cut one where something changed.
						</p>
					{/each}

					<!-- What sits before the first cut. Said rather than swept into an
					     opening chapter nobody asked for. -->
					{#if album.uncut > 0}
						<p class="mt-2.5 px-2 text-[12px] text-neutral-600">
							{album.uncut}
							{album.uncut === 1 ? 'line' : 'lines'} before the first cut.
						</p>
					{/if}
				</div>

				{#if cutting}
					<!-- Twelve months, not a list of the ones with writing in them:
					     you cut where something *began*, and that is not always a day
					     you wrote on. The months you did write in are marked, because
					     they are where you are usually aiming. -->
					<div class="flex max-w-[68ch] flex-wrap gap-1.5">
						{#each MONTH_ABBR as label, m (label)}
							{@const key = `${scope.year}-${String(m + 1).padStart(2, '0')}`}
							{@const already = album.chapters.some((c) => c.month === key)}
							{@const wrote = (album.volumes[m] ?? 0) > 0}
							<button
								type="button"
								disabled={already}
								title={already ? 'already cut here' : `cut a chapter at ${label}`}
								class="flex h-11 w-[64px] flex-col items-center justify-center gap-0.5 text-[11px] transition-colors {already
									? 'text-neutral-500'
									: 'hover:text-ink'} {wrote ? 'text-ink' : 'text-neutral-600'}"
								style="box-shadow:inset 0 0 0 1px var(--color-neutral-{already ? '300' : '400'})"
								onclick={() => {
									cutting = false;
									act(splitChapter(folderId, key, ''));
								}}
							>
								<span class="font-bold tracking-[0.1em]">{label}</span>
								<span class="tabular-nums opacity-70">{album.volumes[m] || ''}</span>
							</button>
						{/each}
					</div>
					<button
						type="button"
						class="self-start px-2 text-[12px] text-neutral-600 transition-colors hover:text-ink"
						onclick={() => (cutting = false)}
					>
						never mind
					</button>
				{:else if scope.year !== 'all'}
					<button
						type="button"
						class="flex h-11 w-fit items-center gap-2 px-4 text-[13px] text-neutral-800 transition-colors hover:text-ink"
						style="box-shadow:inset 0 0 0 1px var(--color-neutral-400)"
						onclick={() => (cutting = true)}
					>
						<span class="text-[15px] leading-none">+</span>
						Cut a chapter
					</button>
				{/if}
			</section>

			<!-- ═══ Patterns ══════════════════════════════════════════════════
			     How often each `\pattern` was written in here. Counted and drawn,
			     never interpreted: no target, no trend, no verdict about what a
			     month of `\stuck` meant. -->
			{#if album.sentiments.length}
				<section class="mt-10 flex max-w-[520px] shrink-0 flex-col gap-3">
					<h2 class="text-[10px] font-bold tracking-[0.18em] text-neutral-600 uppercase">
						Patterns
					</h2>
					{#each album.sentiments as pattern (pattern.name)}
						{@const peak = Math.max(1, ...album.sentiments.map((p) => p.count))}
						<div class="flex items-center gap-3">
							<span class="w-[96px] shrink-0 truncate font-mono text-[13px] text-neutral-800">
								\{pattern.name}
							</span>
							<span class="flex h-[9px] min-w-0 flex-1 items-center">
								<span
									class="h-[9px] bg-neutral-600"
									style="width:{Math.max(3, (pattern.count / peak) * 100)}%"
								></span>
							</span>
							<span class="w-[34px] shrink-0 text-right text-[12px] text-neutral-600 tabular-nums">
								{pattern.count}
							</span>
						</div>
					{/each}
				</section>
			{/if}

			<!-- ═══ Hours ═════════════════════════════════════════════════════
			     Twelve bars of time, beside the twelve bars of lines the reading
			     lens's index draws. A different fact, which is why it is not the
			     same bar: one counts what you wrote, this one counts how long
			     you sat there. -->
			{#if album.seconds > 0}
				<section class="mt-10 flex max-w-[520px] shrink-0 flex-col gap-3">
					<h2 class="text-[10px] font-bold tracking-[0.18em] text-neutral-600 uppercase">
						Hours · {duration(album.seconds)}
					</h2>
					<div class="flex items-end gap-1.5" style="height:64px">
						{#each album.time_volumes as secs, m (m)}
							{@const peak = Math.max(1, ...album.time_volumes)}
							<div class="flex min-w-0 flex-1 flex-col items-center gap-1.5">
								<span
									class="w-full"
									style="height:{secs ? Math.max(3, (secs / peak) * 44) : 1}px;
									       background:var(--color-neutral-{secs ? '600' : '400'})"
									title={secs ? `${MONTH_ABBR[m]} · ${duration(secs)}` : `${MONTH_ABBR[m]} · nothing`}
								></span>
								<span class="text-[9px] tracking-[0.06em] text-neutral-600">
									{MONTH_ABBR[m].slice(0, 1)}
								</span>
							</div>
						{/each}
					</div>
				</section>
			{/if}

			{#if folder}
				<section class="mt-10 flex shrink-0 flex-col gap-3">
					<h2 class="text-[10px] font-bold tracking-[0.18em] text-neutral-600 uppercase">
						Pointing here · {folder.tags.length}
					</h2>
					<div class="flex flex-wrap gap-1.5">
						{#each folder.tags as tag (tag)}
							<button
								type="button"
								title="stop pointing it here"
								class="h-11 px-3.5 font-mono text-[14px] text-neutral-800 transition-colors hover:text-ink"
								style="box-shadow:inset 0 0 0 1px var(--color-neutral-500)"
								onclick={() => act(patchFolder(folder!.id, { remove_tags: [tag] }))}
							>
								{`<${tag}>`}
							</button>
						{:else}
							<span class="text-[13px] text-neutral-600">No tag points here yet.</span>
						{/each}
					</div>
				</section>

				<section class="mt-8 flex shrink-0 flex-col gap-3">
					<h2 class="text-[10px] font-bold tracking-[0.18em] text-neutral-600 uppercase">
						Unclaimed · {unassigned.length}
					</h2>
					<!-- The trip to `/mapping` this lens exists to remove. Pointing a tag
					     here is retroactive: every line ever written with it joins, with
					     nothing migrated, because membership is resolved and never
					     stored. -->
					<div class="flex flex-wrap gap-1.5">
						{#each unassigned.slice(0, 24) as tag (tag.tag)}
							<button
								type="button"
								title="point it here"
								class="flex h-11 items-center gap-2 px-3.5 font-mono text-[14px] text-neutral-700 transition-colors hover:text-ink"
								style="box-shadow:inset 0 0 0 1px var(--color-neutral-400)"
								onclick={() => act(patchFolder(folder!.id, { add_tags: [tag.tag] }))}
							>
								{`<${tag.tag}>`}<span class="text-[11px] text-neutral-600">{tag.count}</span>
							</button>
						{:else}
							<span class="text-[13px] text-neutral-600">Every tag written points somewhere.</span>
						{/each}
					</div>
				</section>

				<!-- Delete lives on the held panel and here both: the panel is where
				     you reach a folder you are *not* reading, and a dossier that can
				     do everything but end the thing it describes sends you hunting
				     for a gesture.

				     Not in the error red, destructive though it is. Red in this app
				     means a refusal — the one colour that is never folded onto the
				     ramp — and spending it on a button that works would make the
				     refusals read as buttons. The confirm is what guards this. -->
				<button
					type="button"
					class="mt-10 self-start text-[12px] font-semibold text-accent-700"
					onclick={() => removeFolder(folder!.id)}
				>
					Delete this folder
				</button>
			{/if}
		{/if}
	</main>
</div>

{#if chapterPanel}
	{@const held = chapterPanel}
	<ChapterPanel
		x={held.x}
		y={held.y}
		chapter={held.chapter}
		armed={held.armed}
		onrename={(to, at) => act(splitChapter(folderId, at, to))}
		onremove={(at) => act(unsplitChapter(folderId, at))}
		onclose={() => (chapterPanel = null)}
	/>
{/if}

{#if heldPicture && folder}
	{@const at = heldPicture}
	{@const owner = folder}
	<HoldMenu x={at.x} y={at.y} width={230} onclose={() => (heldPicture = null)}>
		<button
			type="button"
			class="text-left text-[13px] font-semibold text-accent-700"
			onclick={() => {
				// The request first: clearing `heldPicture` tears down the block
				// this handler is declared in, `@const` bindings and all.
				act(patchFolder(owner.id, { overview_media: '' }));
				heldPicture = null;
			}}
		>
			Remove picture
			<span class="mt-0.5 block text-[11px] font-normal text-neutral-700">
				the photograph stays in the log
			</span>
		</button>
	</HoldMenu>
{/if}

{#if heldPicture && folder}
	{@const at = heldPicture}
	{@const owner = folder}
	<HoldMenu x={at.x} y={at.y} width={230} onclose={() => (heldPicture = null)}>
		<button
			type="button"
			class="text-left text-[13px] font-semibold text-accent-700"
			onclick={() => {
				// The request first: clearing `heldPicture` tears down the block
				// this handler is declared in, `@const` bindings and all.
				act(patchFolder(owner.id, { overview_media: '' }));
				heldPicture = null;
			}}
		>
			Remove picture
			<span class="mt-0.5 block text-[11px] font-normal text-neutral-700">
				the photograph stays in the log
			</span>
		</button>
	</HoldMenu>
{/if}
