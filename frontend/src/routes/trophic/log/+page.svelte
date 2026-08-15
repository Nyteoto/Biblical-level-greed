<script lang="ts">
	/**
	 * The log — Trophic's viewport onto what the capture bar made.
	 * Ported from the `daily` section of `screens/FoldersClient.tsx`.
	 *
	 * Layout is the source's and is load-bearing: a fixed-height pane with the
	 * ruler down one side and the entries beside it, the newest at the top,
	 * fading out at the bottom edge rather than ending on a hard line. On a
	 * wide screen the pane is pushed down so its middle lands at the middle of
	 * the screen — the centre arrow is where your eye already is.
	 *
	 * Selection comes from the ruler, not from clicking a day in a list. Span
	 * (day / week / month) changes what one selection means: a single day, or
	 * the seven / thirty days ending on it, with date dividers between groups.
	 *
	 * The folder list lives below the log, as it does in the source — the two
	 * are one screen there, and the reason is worth keeping: you decide a
	 * folder is needed while reading, not while filing.
	 */
	import EntryRow from '$lib/trophic/EntryRow.svelte';
	import FolderAssignMenu from '$lib/trophic/FolderAssignMenu.svelte';
	import TimelineNav from '$lib/trophic/TimelineNav.svelte';
	import { deviceType, handMode } from '$lib/trophic/device.svelte';
	import { longpress } from '$lib/trophic/longpress';
	import type { ViewSpan } from '$lib/trophic/timeline-draw';
	import {
		assignEntry,
		createFolder,
		deleteFolder,
		getDates,
		getEntries,
		getFolders,
		patchFolder,
		toggleLine,
		type Entry,
		type Folder
	} from '$lib/trophic/api';

	let dates = $state<Record<string, number>>({});
	let entries = $state<Entry[]>([]);
	let selectedDay = $state<string | null>(null);
	let viewSpan = $state<ViewSpan>('day');
	let cumulative = $state<{
		folders: { name: string; count: number }[];
		word_count: number;
		sentiments: { name: string; total: number; dow: number[] }[];
	} | null>(null);
	let error = $state<string | null>(null);
	let isMobile = $state(false);

	// The folder list below the log.
	let folders = $state<Folder[]>([]);
	let creating = $state(false);
	let newName = $state('');
	let menuOpenId = $state<string | null>(null);
	let renamingId = $state<string | null>(null);
	let renameValue = $state('');
	let assignMenu = $state<{ x: number; y: number; entry: Entry } | null>(null);

	// Panel state is a preference, not user data: localStorage, like the source.
	let showFolders = $state(true);
	let showSentiment = $state(true);
	let activeSentiment = $state<string | null>(null);
	let pickerOpen = $state(false);

	const todayKey = new Date().toISOString().slice(0, 10);

	// On a phone the ruler moves to the thumb's side. `handMode` defaults to
	// right and is persisted; the source reads it the same way and has no UI
	// for setting it either, so this port does not invent one.
	const hand = handMode();
	const timelineRight = $derived(isMobile && hand.mode === 'right');

	$effect(() => {
		isMobile = deviceType().isMobile;
		try {
			showFolders = localStorage.getItem('trophic-show-folders') !== '0';
			showSentiment = localStorage.getItem('trophic-show-sentiment') !== '0';
			activeSentiment = localStorage.getItem('trophic-sentiment');
		} catch {
			/* ignore */
		}
		refreshFolders();
		getDates()
			.then((d) => {
				dates = d.dates;
				// Open on the most recent day that has anything in it, so the log
				// never greets you with an empty pane.
				if (!selectedDay) {
					const keys = Object.keys(d.dates).sort();
					if (keys.length) selectedDay = keys[keys.length - 1];
				}
			})
			.catch((e) => (error = String(e)));
	});

	const span = $derived.by(() => {
		if (!selectedDay) return null;
		if (viewSpan === 'day') return { start: selectedDay, end: selectedDay };
		const days = viewSpan === 'week' ? 7 : 30;
		const anchor = new Date(selectedDay + 'T00:00:00Z');
		anchor.setUTCDate(anchor.getUTCDate() - (days - 1));
		return { start: anchor.toISOString().slice(0, 10), end: selectedDay };
	});

	// Refetch whenever the window moves. Keyed on the resolved span so a scroll
	// that does not cross a day boundary does not hit the API.
	let lastKey = '';
	$effect(() => {
		const s = span;
		if (!s) return;
		const key = `${s.start}:${s.end}`;
		if (key === lastKey) return;
		lastKey = key;
		const req =
			viewSpan === 'day' ? getEntries({ date: s.start }) : getEntries({ from: s.start, to: s.end });
		req.then((r) => (entries = r.entries)).catch((e) => (error = String(e)));
		fetch(`/api/capture/cumulative?up_to=${s.end}`)
			.then((r) => (r.ok ? r.json() : null))
			.then((c) => (cumulative = c))
			.catch(() => {});
	});

	function formatDateLabel(key: string): string {
		if (key === todayKey) return 'today';
		const [y, m, d] = key.split('-').map(Number);
		return new Date(y, m - 1, d).toLocaleDateString(undefined, {
			weekday: 'short',
			month: 'short',
			day: 'numeric'
		});
	}

	/** Newest day first, entries already newest-first inside it. */
	const groups = $derived.by(() => {
		const map = new Map<string, Entry[]>();
		for (const e of entries) {
			if (!map.has(e.day)) map.set(e.day, []);
			map.get(e.day)!.push(e);
		}
		return [...map.entries()]
			.sort((a, b) => b[0].localeCompare(a[0]))
			.map(([day, list]) => ({ day, entries: list }));
	});

	async function onToggle(entry: Entry, line: number) {
		try {
			const { entry: updated } = await toggleLine(entry.id, line);
			entries = entries.map((e) => (e.id === updated.id ? updated : e));
		} catch (e) {
			error = String(e);
		}
	}

	const activeSentimentData = $derived(
		cumulative?.sentiments.find((s) => s.name === activeSentiment) ?? cumulative?.sentiments[0]
	);

	const DOW = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

	function persist(key: string, value: string) {
		try {
			localStorage.setItem(key, value);
		} catch {
			/* ignore */
		}
	}

	// ── Folders ───────────────────────────────────────────────────────────

	async function refreshFolders() {
		try {
			folders = (await getFolders()).folders;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	async function act(work: Promise<unknown>) {
		error = null;
		try {
			await work;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		await refreshFolders();
	}

	async function submitNewFolder(e: SubmitEvent) {
		e.preventDefault();
		const name = newName.trim();
		if (!name) return;
		newName = '';
		creating = false;
		await act(createFolder(name));
	}

	async function submitRename(id: string) {
		const name = renameValue.trim();
		renamingId = null;
		if (!name) return;
		await act(patchFolder(id, { name }));
	}

	async function refile(entry: Entry, folderId: string | null) {
		error = null;
		try {
			const { entry: updated } = await assignEntry(entry.id, folderId);
			entries = entries.map((e) => (e.id === updated.id ? updated : e));
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	/**
	 * Double-click anywhere that is not the log or the folder list to start a
	 * folder. The source's one hidden gesture, kept because the ghost card at
	 * the end of the list is what teaches it.
	 */
	function onDoubleClick(event: MouseEvent) {
		const target = event.target as HTMLElement;
		if (target.closest('[data-daily-section]') || target.closest('[data-folder-list]')) return;
		if (creating || renamingId || menuOpenId) return;
		creating = true;
	}

	const emptyMessage = $derived(
		Object.keys(dates).length === 0
			? 'capture something to see it here.'
			: viewSpan === 'day'
				? 'quiet day.'
				: viewSpan === 'week'
					? 'quiet week.'
					: 'quiet month.'
	);
</script>

<svelte:window
	onclick={() => {
		pickerOpen = false;
		menuOpenId = null;
	}}
/>

<header
	class="sticky top-0 z-40 flex items-center justify-between bg-[#14100c] px-6 py-5 text-[11px] tracking-wide text-stone-500"
>
	<a href="/trophic" class="transition-colors hover:text-stone-300">← capture</a>
	<span class="text-stone-300">log</span>
	<button
		type="button"
		class="transition-colors hover:text-stone-300"
		onclick={() => (creating = !creating)}
	>
		{creating ? 'cancel' : '+ new'}
	</button>
</header>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<main
	class="mx-auto flex w-full max-w-xl flex-1 flex-col gap-6 px-6 pb-20"
	ondblclick={onDoubleClick}
>
	<section data-daily-section class="flex flex-col gap-3 md:pt-[calc(50vh-540px)]">
		<div class="text-[10px] tracking-[0.15em] text-stone-500 uppercase">daily</div>
		<div class="text-[11px] text-stone-400">
			{#if selectedDay && span}
				{viewSpan === 'day'
					? formatDateLabel(selectedDay)
					: `${formatDateLabel(span.start)} — ${formatDateLabel(span.end)}`}
				{#if viewSpan !== 'day'}<span class="ml-2 text-stone-600">({viewSpan})</span>{/if}
			{:else}
				—
			{/if}
		</div>

		<div class="flex gap-3 {timelineRight ? 'flex-row-reverse' : ''}" style="height:520px">
			<TimelineNav
				{dates}
				selected={selectedDay}
				bind:viewSpan
				dense={isMobile}
				onselect={(d) => (selectedDay = d)}
			/>
			<div class="relative flex-1">
				<div class="trophic-scrollbar-hide h-full overflow-y-auto">
					{#if entries.length > 0}
						{@const showHeaders = viewSpan !== 'day'}
						<div class="flex flex-col gap-1">
							{#each groups as g, gi (g.day)}
								<div>
									{#if showHeaders && gi > 0}
										<div class="my-2 border-t border-dashed border-stone-800"></div>
									{/if}
									{#if showHeaders}
										<div class="mb-1 text-[10px] text-stone-500">{formatDateLabel(g.day)}</div>
									{/if}
									{#each g.entries as e, i (e.id)}
										<!-- Right-click, or long-press on a phone: file this line
										     into a folder without having tagged it. -->
										<div
											class="py-0.5"
											use:longpress={(x, y) => (assignMenu = { x, y, entry: e })}
										>
											<EntryRow entry={e} index={i} ontoggle={(line) => onToggle(e, line)} />
										</div>
									{/each}
								</div>
							{/each}
						</div>
					{:else}
						<p class="text-[11px] text-stone-500">{emptyMessage}</p>
					{/if}
				</div>
				<!-- The list fades out at the bottom rather than being cut off. -->
				<div
					class="pointer-events-none absolute right-0 bottom-0 left-0 h-16"
					style="background:linear-gradient(to bottom, transparent, #14100c)"
				></div>
			</div>
		</div>

		{#if error}
			<p class="text-[11px] text-red-400">{error}</p>
		{/if}

		<!-- Cumulative readings. Stored and drawn, never interpreted. -->
		<div style="min-height:32px">
			{#if cumulative && (cumulative.word_count > 0 || cumulative.folders.length > 0)}
				<div class="flex flex-col gap-4 text-[11px]">
					<span class="text-stone-500">{cumulative.word_count.toLocaleString()} words</span>

					{#if cumulative.folders.length > 0}
						{@const max = Math.max(...cumulative.folders.map((f) => f.count))}
						<div class="flex flex-col gap-3">
							<button
								type="button"
								class="self-start rounded bg-stone-800 px-2.5 py-1 text-[10px] tracking-wide text-stone-400 transition-colors hover:bg-stone-700"
								onclick={() => {
									showFolders = !showFolders;
									persist('trophic-show-folders', showFolders ? '1' : '0');
								}}
							>
								folders {showFolders ? '▾' : '▸'}
							</button>
							{#if showFolders}
								<div class="flex flex-col gap-1.5">
									{#each cumulative.folders as f (f.name)}
										<div
											class="flex items-center gap-2"
											title="{f.count} entries tagged <{f.name}> up to this point"
										>
											<span class="w-24 shrink-0 truncate text-right" style="color:#60a5fa"
												>{`<${f.name}>`}</span
											>
											<div class="h-[6px] flex-1 overflow-hidden rounded-full bg-stone-800">
												<div
													class="h-full rounded-full transition-all duration-500"
													style="width:{(f.count / max) * 100}%;background:#60a5fa"
												></div>
											</div>
											<span class="w-6 shrink-0 text-right text-stone-500 tabular-nums"
												>{f.count}</span
											>
										</div>
									{/each}
								</div>
							{/if}
						</div>
					{/if}

					{#if activeSentimentData}
						{@const s = activeSentimentData}
						{@const peak = Math.max(...s.dow, 0.01)}
						<div class="flex flex-col gap-3">
							<div class="flex items-center gap-2">
								<button
									type="button"
									class="rounded bg-stone-800 px-2.5 py-1 text-[10px] tracking-wide text-stone-400 transition-colors hover:bg-stone-700"
									onclick={() => {
										showSentiment = !showSentiment;
										persist('trophic-show-sentiment', showSentiment ? '1' : '0');
									}}
								>
									sentiment {showSentiment ? '▾' : '▸'}
								</button>
								{#if showSentiment}
									<div class="relative">
										<button
											type="button"
											class="rounded bg-rose-500/15 px-2.5 py-1 text-[10px] tracking-wide text-rose-300 transition-colors hover:bg-rose-500/25"
											onclick={(e) => {
												e.stopPropagation();
												pickerOpen = !pickerOpen;
											}}
										>
											{`\\${s.name} ▾`}
										</button>
										{#if pickerOpen}
											<div
												class="absolute top-full left-0 z-50 mt-1 min-w-[120px] rounded border border-stone-700 bg-[#1b1613] py-1 shadow-lg"
											>
												{#each cumulative.sentiments as opt (opt.name)}
													<button
														type="button"
														class="w-full px-3 py-1.5 text-left text-[11px] transition-colors hover:bg-stone-800 {opt.name ===
														s.name
															? 'text-rose-300'
															: 'text-stone-400'}"
														onclick={() => {
															activeSentiment = opt.name;
															persist('trophic-sentiment', opt.name);
															pickerOpen = false;
														}}
													>
														{`\\${opt.name}`}<span class="ml-2 text-stone-600">{opt.total}</span>
													</button>
												{/each}
											</div>
										{/if}
									</div>
								{/if}
							</div>
							{#if showSentiment}
								<div class="flex justify-center py-1">
									<div
										class="flex items-end gap-3 pt-3"
										title="average \{s.name} per weekday up to this point"
									>
										{#each s.dow as v, i (i)}
											<div class="flex flex-col items-center gap-1" style="width:20px">
												<span
													class="text-[9px] leading-none text-stone-500 tabular-nums"
													style="opacity:{v > 0 ? 1 : 0}"
												>
													{v % 1 === 0 ? v : v.toFixed(1)}
												</span>
												<div
													class="w-full rounded-t bg-rose-400/80 transition-all duration-500"
													style="height:{Math.max((v / peak) * 56, v > 0 ? 2 : 0)}px"
												></div>
												<span class="text-[8px] leading-none text-stone-600">{DOW[i]}</span>
											</div>
										{/each}
									</div>
								</div>
							{/if}
						</div>
					{/if}
				</div>
			{/if}
		</div>
	</section>

	<!-- ── Folders ──────────────────────────────────────────────────────── -->
	<section class="flex flex-col gap-3">
		<div class="flex items-baseline justify-between">
			<div class="text-[10px] tracking-[0.15em] text-stone-500 uppercase">folders</div>
			<a href="/trophic/mapping" class="text-[10px] text-stone-500 hover:text-stone-300">
				mapping →
			</a>
		</div>

		{#if creating}
			<form class="flex items-baseline gap-3" onsubmit={submitNewFolder}>
				<!-- svelte-ignore a11y_autofocus -->
				<input
					autofocus
					bind:value={newName}
					placeholder="folder name"
					class="flex-1 border-b border-stone-700 bg-transparent py-2 text-sm text-stone-200 transition-colors focus:border-stone-500 focus:outline-none"
					style="caret-color:#e7e5e4"
					onkeydown={(e) => {
						if (e.key === 'Escape') creating = false;
					}}
				/>
				<button type="submit" class="text-[11px] text-stone-400 hover:text-stone-200">
					create
				</button>
			</form>
		{/if}

		{#if folders.length === 0 && !creating}
			<p class="text-[11px] leading-relaxed text-stone-500">
				no folders yet. create one, then point tags at it from
				<a href="/trophic/mapping" class="text-stone-400 hover:text-stone-200">mapping</a>.
			</p>
		{/if}

		<div class="flex flex-col gap-2" data-folder-list>
			{#each folders as f (f.id)}
				<div
					class="folder-card relative flex min-w-0 items-center justify-between rounded bg-stone-900 px-5 py-4"
					style={menuOpenId === f.id ? 'z-index:50' : ''}
				>
					{#if renamingId === f.id}
						<form
							class="flex flex-1 items-center gap-2"
							onsubmit={(e) => {
								e.preventDefault();
								submitRename(f.id);
							}}
						>
							<!-- svelte-ignore a11y_autofocus -->
							<input
								autofocus
								bind:value={renameValue}
								class="flex-1 border-b border-stone-600 bg-transparent py-0 text-sm text-stone-100 focus:border-stone-400 focus:outline-none"
								style="caret-color:#fafaf9"
								onblur={() => submitRename(f.id)}
								onkeydown={(e) => {
									if (e.key === 'Escape') renamingId = null;
								}}
							/>
						</form>
					{:else}
						<a
							href="/trophic/folders/{f.id}"
							class="flex min-w-0 flex-1 items-center gap-2.5 text-sm text-stone-100"
						>
							<span class="h-2 w-2 shrink-0 rounded-full" style="background:{f.color}"></span>
							<span class="shrink-0 truncate">{f.name}</span>
							{#if f.tags.length > 0}
								<span class="truncate text-[10px] text-stone-500">
									{f.tags.map((t) => `<${t}>`).join(' ')}
								</span>
							{/if}
						</a>
						<button
							type="button"
							class="ml-2 shrink-0 px-2 py-1 text-sm text-stone-500 transition-colors hover:text-stone-300"
							aria-label="folder options"
							onclick={(e) => {
								e.stopPropagation();
								menuOpenId = menuOpenId === f.id ? null : f.id;
							}}
						>
							···
						</button>
					{/if}

					{#if menuOpenId === f.id}
						<!-- No stopPropagation here: both items close the menu themselves,
						     so letting the click reach the window costs nothing. -->
						<div
							class="absolute top-full right-1 z-[100] mt-1 min-w-[130px] rounded border border-stone-700 bg-[#1b1613] py-1.5 shadow-xl"
						>
							<button
								type="button"
								class="w-full px-4 py-2 text-left text-[12px] text-stone-300 transition-colors hover:bg-stone-800 hover:text-stone-100"
								onclick={() => {
									menuOpenId = null;
									renameValue = f.name;
									renamingId = f.id;
								}}
							>
								rename
							</button>
							<button
								type="button"
								class="w-full px-4 py-2 text-left text-[12px] text-red-400 transition-colors hover:bg-stone-800 hover:text-red-300"
								onclick={() => {
									menuOpenId = null;
									act(deleteFolder(f.id));
								}}
							>
								delete
							</button>
						</div>
					{/if}
				</div>
			{/each}

			{#if !creating}
				<div
					class="flex items-center justify-center rounded border border-dashed border-stone-800 px-5 py-4 text-[11px] text-stone-600 select-none"
				>
					{isMobile ? 'double-tap' : 'double-click'} anywhere to create a folder
				</div>
			{/if}
		</div>
	</section>
</main>

{#if assignMenu}
	{@const target = assignMenu.entry}
	<FolderAssignMenu
		x={assignMenu.x}
		y={assignMenu.y}
		{folders}
		current={target.manual_folders[0] ?? null}
		onselect={(folderId) => refile(target, folderId)}
		onclear={() => refile(target, null)}
		onclose={() => (assignMenu = null)}
	/>
{/if}
