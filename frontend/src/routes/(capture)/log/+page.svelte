<script lang="ts">
	/**
	 * The year shelf — the top of the tree.
	 *
	 * What this screen answers, and what the flat feed it replaced could not:
	 * which albums exist this year, how big each one is, and when each was
	 * busy. Three questions you cannot answer by scrolling, which is the whole
	 * argument for it. **Scrolling is for reading, never for travelling** — the
	 * year rail, the jump field and the cards are all constant-cost, and none
	 * of them gets slower as the journal gets longer.
	 *
	 * An album is a folder seen through one year, and that pairing is stored
	 * nowhere: every count, mosaic and sparkline here comes back from
	 * `/api/capture/shelf`, which recomputes all of it from the day keys. That
	 * is why "albums restart each year" can be a switch in Settings rather than
	 * a migration — turning it off passes `all` and the same read answers.
	 *
	 * The one thing this screen deliberately will not do is show entries. It is
	 * an index; reading happens one album down.
	 */
	import { untrack } from 'svelte';
	import { goto } from '$app/navigation';
	import Mosaic from '$lib/trophic/Mosaic.svelte';
	import TabPill from '$lib/trophic/TabPill.svelte';
	import { logSettings } from '$lib/trophic/settings.svelte';
	import { pixelate } from '$lib/trophic/pixelate';
	import {
		createFolder,
		deleteFolder,
		getShelf,
		getUnassignedTags,
		patchFolder,
		setFolderGroup,
		renameGroup,
		deleteGroup,
		type Album,
		type Folder,
		type Shelf,
		type UnassignedTag
	} from '$lib/trophic/api';
	import FolderPanel from '$lib/trophic/FolderPanel.svelte';
	import GroupPanel from '$lib/trophic/GroupPanel.svelte';
	import { collapsedGroups } from '$lib/trophic/collapsed.svelte';
	import Glyph from '$lib/trophic/Glyph.svelte';
	import { holdable } from '$lib/trophic/holdable';

	let { data }: { data: { shelf?: Shelf; key?: string } } = $props();

	// `+page.ts` decides whether `/log` is even the right screen, and redirects
	// before this component exists when it is not. When it does not redirect it
	// has already read the shelf, so this starts populated rather than repeating
	// the request a frame later.
	// `untrack` because the seed is meant to be the *initial* value and nothing
	// else: this component is reused across `?year=` changes, and re-seeding from
	// a stale `data` on one of those would put the previous year back on screen.
	let shelf = $state<Shelf | null>(untrack(() => data.shelf ?? null));
	let error = $state<string | null>(null);
	/** The new-folder tile, which is a button until it is a name field. */
	let creating = $state(false);
	let newName = $state('');
	/** Held a card: the same properties panel the album sidebar opens. */
	let panel = $state<{ folder: Folder; x: number; y: number } | null>(null);
	/** A held group heading. Separate from `panel` because the two are
	 *  different objects with different powers, and one nullable union would
	 *  make every read of either ask which it was. */
	let groupPanel = $state<{ name: string; x: number; y: number } | null>(null);
	let unassigned = $state<UnassignedTag[]>([]);
	let loading = $state(true);
	let jump = $state('');

	const thisYear = String(new Date().getFullYear());
	let year = $state(thisYear);

	// What the display numeral says. Named because it is read twice: once to
	// draw, and once as the `{#key}` that redraws it — `pixelate` reads its
	// element's text when the action is created, so the element has to be new
	// when the year changes.
	const shelfYear = $derived(logSettings.yearAlbums ? (shelf?.year ?? year) : 'All');

	$effect(() => {
		logSettings.hydrate();
	});

	// Keyed on the only two things that decide what comes back, so nothing
	// refetches when the jump field is typed in.
	let lastKey = untrack(() => data.key ?? '');
	$effect(() => {
		const key = logSettings.yearAlbums ? year : 'all';
		if (key === lastKey) return;
		lastKey = key;
		load(key);
		getUnassignedTags()
			.then((u) => (unassigned = u.tags))
			.catch(() => {});
	});

	async function load(key: string) {
		loading = true;
		error = null;
		try {
			shelf = await getShelf(key);
			// A fresh install, or a year the rail offered that has since been
			// emptied: fall to the newest year that exists rather than showing
			// an empty shelf under a heading that says 2026.
			if (shelf.albums.length === 0 && shelf.unfiled === 0 && shelf.years.length > 0) {
				if (logSettings.yearAlbums && !shelf.years.includes(year)) {
					year = shelf.years[0];
					lastKey = '';
				}
			}
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		loading = false;
	}

	/** Re-read the shelf after something changed it. `lastKey` is the latch the
	 *  loading effect uses to avoid refetching on every keystroke in the jump
	 *  field, so clearing it is how anything else asks for a fresh read. */
	function refresh() {
		lastKey = '';
		load(logSettings.yearAlbums ? year : 'all');
		// The loose tags travel with the shelf: the panel offers them for mapping,
		// and they are the one thing on it not about a single folder.
		getUnassignedTags()
			.then((u) => (unassigned = u.tags))
			.catch(() => {
				/* the panel simply offers nothing to map */
			});
	}

	async function act(work: Promise<unknown>) {
		panel = null;
		groupPanel = null;
		error = null;
		try {
			await work;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		refresh();
	}

	function removeFolder(id: string) {
		// The folder, not what was written into it — the entries stay and their
		// tags go back in the unassigned pool.
		if (!confirm('Delete this folder? Its entries stay in the log.')) return;
		act(deleteFolder(id));
	}

	async function submitNewFolder(event: SubmitEvent) {
		event.preventDefault();
		const name = newName.trim();
		if (!name) {
			creating = false;
			return;
		}
		try {
			// No tags passed: a folder claims the tag of its own name at creation,
			// so `New folder → Garden` is already collecting `<garden>` before you
			// have opened the mapping screen. See TROPHIC.md.
			const { folder } = await createFolder(name);
			// And it starts `running`, which is not an assumption about what you
			// meant — it is the only way the thing you just made is on the screen
			// you made it from. The shelf drops albums with nothing in them this
			// year *unless* they are active, precisely so that "a project just
			// started has nothing in it yet and is still the thing you are doing".
			// Without this the button appears to do nothing at all. It is one tap
			// to clear the state again, in the album's own options.
			await patchFolder(folder.id, { state: 'active' });
			newName = '';
			creating = false;
			error = null;
			refresh();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	const albumHref = (id: string | null) =>
		`/folders/${id ?? 'unfiled'}?year=${shelf?.year ?? 'all'}`;

	const folded = collapsedGroups();

	/** The shelf in two parts: what has no group, then the named groups in the
	 *  order the backend gives them. Ungrouped stays on top and keeps the plain
	 *  grid, so a shelf nobody has arranged looks exactly as it did before
	 *  groups existed — nothing is gained by making you scroll past an empty
	 *  ceremonial heading to reach your folders.
	 */
	const ungrouped = $derived(shelf?.albums.filter((a) => !a.group) ?? []);
	const sections = $derived(
		(shelf?.groups ?? []).map((name) => ({
			name,
			albums: shelf?.albums.filter((a) => a.group === name) ?? []
		}))
	);

	/** Big cards for what is running, one-line strips for what is not. The
	 *  split is by size rather than by state: an album with three entries in it
	 *  does not earn a mosaic even if the folder is marked active.
	 *
	 *  Applied per section rather than across the shelf. A group is a shelf of
	 *  its own once you have made one, and ranking its cards against another
	 *  group's would mean a group of small folders never got a mosaic at all.
	 */
	const LEAD = 3;
	const split = (albums: Album[]) => ({
		lead: albums.slice(0, LEAD),
		quiet: albums.slice(LEAD)
	});

	const STATE_WORD: Record<string, string> = { active: 'running', shipped: 'shipped' };

	function submitJump(event: SubmitEvent) {
		event.preventDefault();
		const query = jump.trim();
		if (!query) return;
		// A date goes to the day it names; anything else is a word, and the
		// album whose name or tags match it is the best guess. Both land on a
		// screen that can read, which is the point of the field.
		const day = query.match(/^\d{4}-\d{2}-\d{2}$/);
		if (day) {
			goto(`/folders/unfiled?year=${query.slice(0, 4)}&day=${query}`);
			return;
		}
		const needle = query.toLowerCase().replace(/^[<\\]|>$/g, '');
		const hit = shelf?.albums.find(
			(a) => a.name.toLowerCase().includes(needle) || a.tags.some((t) => t.includes(needle))
		);
		if (hit) goto(albumHref(hit.id));
		else error = `nothing here matches “${query}”`;
	}
</script>

<div class="flex min-h-dvh flex-col">
	<!-- The nav pill sits in the page's own corner here, as it does on every
	     other screen. It was inside the content column, which put it a rail's
	     width further right than anywhere else in the app. -->
	<div class="shrink-0 px-[34px] pt-[22px]">
		<TabPill />
	</div>

	<div class="flex min-h-0 flex-1">
		<!-- The year rail. Two digits is enough — the heading spells the year out
		     in full a few centimetres away, and the rail is a place you learn the
		     position of rather than read. There is no label over it: it was a
		     vertical wordmark saying TROPHIC LOG on the Log screen of an app
		     called Trophic, which is the definition of noise. -->
		<div class="flex w-[92px] shrink-0 flex-col items-center gap-1.5 py-[26px]">
			{#each shelf?.years ?? [] as y (y)}
				{@const on = logSettings.yearAlbums && y === shelf?.year}
				<button
					type="button"
					class="rounded-[12px] px-3 py-2.5 text-[15px] transition-colors {on
						? 'accent-fill font-extrabold'
						: 'font-semibold text-neutral-700 hover:text-ink'}"
					onclick={() => {
						logSettings.setYearAlbums(true);
						year = y;
					}}
				>
					{y.slice(2)}
				</button>
			{/each}
			<button
				type="button"
				class="mt-auto text-[11px] transition-colors {logSettings.yearAlbums
					? 'text-neutral-600 hover:text-ink'
					: 'font-bold text-accent-700'}"
				title="every year at once"
				onclick={() => logSettings.setYearAlbums(!logSettings.yearAlbums)}
			>
				all
			</button>
		</div>

		<div class="flex min-w-0 flex-1 flex-col gap-[26px] px-[46px] pt-[18px]">
			<div class="flex items-end justify-between gap-6">
				<div class="min-w-0">
					<div class="text-[10px] font-bold tracking-[0.22em] text-accent-700 uppercase">
						Year shelf
					</div>
					<div class="mt-2 flex items-baseline gap-4">
						<!-- The one pixelated thing on the screen. `{#key}` because an action
						     reads its element's text once, and the year changes under it.
						     Tracking went from -0.035em to positive: the negative leading was
						     tuned for Archivo's tight aperture, and mono numerals are wider —
						     at 64px they collided. -->
						{#key shelfYear}
							<h1
								use:pixelate={{ block: 3 }}
								class="text-[64px] leading-[0.9] font-extrabold tracking-[0.02em]"
							>
								{shelfYear}
							</h1>
						{/key}
						{#if shelf}
							<!-- Marks rather than nouns: three numbers and three words was
							     mostly words, and the words never change. -->
							<span
								class="flex items-center gap-3.5 text-[14px] text-neutral-700 tabular-nums"
							>
								<span class="flex items-center gap-1.5">
									<Glyph kind="album" count={shelf.albums.length} />
									{shelf.albums.length}
								</span>
								<span class="flex items-center gap-1.5">
									<Glyph kind="entries" count={shelf.entries} />
									{shelf.entries.toLocaleString()}
								</span>
								<span class="flex items-center gap-1.5">
									<Glyph kind="media" count={shelf.media} />
									{shelf.media.toLocaleString()}
								</span>
							</span>
						{/if}
					</div>
				</div>

				<!-- The floor is a floor only where there is room for one. At phone
				     width a 250px minimum next to the year made the row wider than the
				     screen, and the horizontal scrollbar that raised cost every screen
				     ten pixels of pointless vertical scroll. -->
				<form
					class="focus-pill flex min-w-0 items-center gap-2.5 rounded-[12px] bg-surface px-3.5 py-[11px] shadow-sm sm:min-w-[250px]"
					onsubmit={submitJump}
				>
					<svg
						width="15"
						height="15"
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.6"
						stroke-linecap="round"
						class="shrink-0 text-neutral-600"
						aria-hidden="true"
					>
						<circle cx="11" cy="11" r="7" /><path d="m20 20-3.6-3.6" />
					</svg>
					<input
						bind:value={jump}
						placeholder="Jump to a date, tag or word"
						class="min-w-0 flex-1 bg-transparent text-[13px] placeholder:text-neutral-700"
					/>
				</form>
			</div>

			{#if error}
				<p class="text-[12px] text-accent-700">{error}</p>
			{/if}

			{#if loading && !shelf}
				<p class="text-[13px] text-neutral-700">reading…</p>
			{:else if shelf && shelf.albums.length === 0 && shelf.unfiled === 0}
				<p class="text-[13px] text-neutral-700">capture something and it will be here.</p>
			{:else if shelf}
				{#snippet cards(list: Album[])}
					{@const part = split(list)}
						<!-- Running albums: a mosaic, a name and a tally. Everything on this
						     card is a derived read. -->
						{#each part.lead as album (album.id)}
							<a
								href={albumHref(album.id)}
								use:holdable={(x, y) => (panel = { folder: album, x, y })}
								class="lift lift-md flex flex-col gap-[13px] rounded-[16px] bg-surface p-4 shadow-md"
							>
								<Mosaic refs={album.lead} />
								<div class="flex items-baseline justify-between gap-2.5">
									<span class="truncate text-[20px] font-bold tracking-[-0.015em]">
										{album.name}
									</span>
									{#if STATE_WORD[album.state]}
										<span
											class="shrink-0 rounded-md bg-accent-100 px-[7px] py-[3px] text-[10px] font-bold tracking-[0.1em] text-accent-700 uppercase"
										>
											{STATE_WORD[album.state]}
										</span>
									{/if}
								</div>
								<div
									class="flex items-baseline justify-between text-[12px] text-neutral-700 tabular-nums"
								>
									<span class="flex items-center gap-3">
										<span class="flex items-center gap-1.5">
											<Glyph kind="entries" count={album.entry_count} size={12} />
											{album.entry_count}
										</span>
										{#if album.media_count}
											<span class="flex items-center gap-1.5">
												<Glyph kind="media" count={album.media_count} size={12} />
												{album.media_count}
											</span>
										{/if}
									</span>
									<span>{album.chapters} {album.chapters === 1 ? 'chapter' : 'chapters'}</span>
								</div>
							</a>
						{/each}

						<!-- Everything else: one row each. Same information, less of it. -->
						{#each part.quiet as album (album.id)}
							<a
								href={albumHref(album.id)}
								use:holdable={(x, y) => (panel = { folder: album, x, y })}
								class="lift lift-sm flex items-center gap-3.5 rounded-[16px] bg-surface p-4 shadow-sm"
							>
								<div class="h-[54px] w-[72px] shrink-0">
									<Mosaic refs={album.lead} single />
								</div>
								<div class="min-w-0 flex-1">
									<div class="truncate text-[17px] font-bold tracking-[-0.01em]">{album.name}</div>
									<div class="mt-[3px] flex items-center gap-1.5 text-[12px] text-neutral-700">
										<Glyph kind="entries" count={album.entry_count} size={12} />
										<span class="tabular-nums">{album.entry_count}</span>
										{#if album.months}<span class="ml-1.5">{album.months}</span>{/if}
									</div>
								</div>
								{#if STATE_WORD[album.state]}
									<span
										class="shrink-0 text-[10px] font-bold tracking-[0.1em] text-neutral-700 uppercase"
									>
										{STATE_WORD[album.state]}
									</span>
								{/if}
							</a>
						{/each}
				{/snippet}

				<!-- Ungrouped first, in the plain grid. A shelf nobody has arranged
				     looks exactly as it did before groups existed. -->
				<div class="grid grid-cols-3 gap-[22px]">
					{@render cards(ungrouped)}

					{#if shelf.unfiled > 0}
						<!-- The pile nothing has claimed. Dashed and unfilled because it
						     is not a project — it is the raw material of one, and the
						     way out of it is Settings → Folders & tags. -->
						<a
							href={albumHref(null)}
							class="flex h-fit w-fit items-center gap-3 self-start rounded-[12px] border border-dashed border-neutral-400 px-3 py-2 text-neutral-700 transition-colors hover:border-neutral-600 hover:text-ink"
						>
							<span class="text-[13px]">
								Unfiled{logSettings.yearAlbums ? ' this year' : ''}
							</span>
							<span class="text-[12px] tabular-nums">{shelf.unfiled}</span>
						</a>
					{/if}

					<!-- New folder. The shelf is where you look at your projects, so it
					     is where you should be able to start one — until now the only
					     two doors were the capture bar offering to fix a `--directive`
					     it did not recognise, and the mapping screen. Neither is
					     somewhere you go to begin something.

					     Square, dashed and unfilled like the unfiled pile, because both
					     are openings rather than things: one is work you have not
					     sorted, the other is a project you have not started. -->
					{#if creating}
						<form
							class="focus-pill flex items-center gap-3 rounded-[16px] border-[1.5px] border-dashed border-accent-700 p-4"
							onsubmit={submitNewFolder}
						>
							<!-- svelte-ignore a11y_autofocus -->
							<input
								autofocus
								bind:value={newName}
								placeholder="name it"
								aria-label="new folder name"
								class="min-w-0 flex-1 bg-transparent text-[15px] font-semibold placeholder:font-normal placeholder:text-neutral-700"
								onkeydown={(e) => {
									if (e.key === 'Escape') {
										creating = false;
										newName = '';
									}
								}}
								onblur={() => {
									if (!newName.trim()) creating = false;
								}}
							/>
							<span class="shrink-0 text-[11px] text-neutral-700">↵</span>
						</form>
					{:else}
						<button
							type="button"
							class="flex h-[86px] w-[86px] items-center justify-center rounded-[16px] border-[1.5px] border-dashed border-neutral-400 text-[26px] leading-none text-neutral-600 transition-colors hover:border-accent-700 hover:text-accent-700"
							title="new folder"
							aria-label="new folder"
							onclick={() => (creating = true)}
						>
							+
						</button>
					{/if}
				</div>

				<!-- Then the named groups, in the order they were first named. A
				     heading is a button over its own grid: the whole row is the
				     hit area, because a chevron alone is a 12px target for a
				     gesture you make constantly. -->
				{#each sections as section (section.name)}
					{@const shut = folded.isShut(shelf.year, section.name)}
					<div class="mt-[34px] flex flex-col gap-[18px]">
						<button
							type="button"
							class="group/head flex w-full items-center gap-2.5 text-left"
							aria-expanded={!shut}
							use:holdable={(x, y) => (groupPanel = { name: section.name, x, y })}
							onclick={() => folded.toggle(shelf?.year ?? null, section.name)}
						>
							<span
								class="inline-block text-[13px] leading-none text-neutral-600 transition-transform duration-150 group-hover/head:text-ink {shut
									? ''
									: 'rotate-90'}"
							>
								▶
							</span>
							<span
								class="text-[11px] font-bold tracking-[0.22em] text-neutral-700 uppercase transition-colors group-hover/head:text-ink"
							>
								{section.name}
							</span>
							<!-- The count is what a folded group still has to say. -->
							<span class="flex items-center gap-1.5 text-[12px] text-neutral-700 tabular-nums">
								<Glyph kind="album" count={section.albums.length} size={12} />
								{section.albums.length}
							</span>
							<span class="h-px flex-1 bg-neutral-300"></span>
						</button>
						{#if !shut}
							<div class="grid grid-cols-3 gap-[22px]">
								{@render cards(section.albums)}
							</div>
						{/if}
					</div>
				{/each}

				<!-- The year below, pinned to the foot, half off the bottom edge:
				     the shelf hands back rather than ending. -->
				{#if shelf.previous}
					{@const before = shelf.previous}
					<button
						type="button"
						class="lift lift-md mt-auto flex items-center gap-5 rounded-t-[16px] bg-surface px-[22px] py-[18px] text-left shadow-md"
						onclick={() => (year = before.year)}
					>
						<span class="text-[22px] font-extrabold tracking-[-0.02em] text-neutral-700">
							{before.year}
						</span>
						<span class="text-[13px] text-neutral-700">
							{before.entries.toLocaleString()} entries
						</span>
						<span class="ml-auto text-[13px] font-semibold">Open year →</span>
					</button>
				{/if}
			{/if}
		</div>
	</div>
</div>

{#if panel}
	{@const open = panel}
	<FolderPanel
		x={open.x}
		y={open.y}
		folder={open.folder}
		{unassigned}
		onpatch={(change) => act(patchFolder(open.folder.id, change))}
		ondelete={() => removeFolder(open.folder.id)}
		onclose={() => (panel = null)}
		year={logSettings.yearAlbums ? (shelf?.year ?? null) : null}
		group={shelf?.albums.find((a) => a.id === open.folder.id)?.group ?? ''}
		groups={shelf?.groups ?? []}
		ongroup={(name) =>
			act(setFolderGroup(open.folder.id, shelf?.year ?? '', name))}
	/>
{/if}

{#if groupPanel && shelf?.year}
	{@const held = groupPanel}
	{@const year = shelf.year}
	<GroupPanel
		x={held.x}
		y={held.y}
		name={held.name}
		{year}
		count={shelf.albums.filter((a) => a.group === held.name).length}
		onrename={(to) => act(renameGroup(year, held.name, to))}
		ondelete={() => act(deleteGroup(year, held.name))}
		onclose={() => (groupPanel = null)}
	/>
{/if}
