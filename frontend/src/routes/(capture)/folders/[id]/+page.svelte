<script lang="ts">
	/**
	 * One folder: what is in it, and what put it there.
	 * Ported from `screens/FolderDetailClient.tsx`.
	 *
	 * The tag chips at the top are the folder's definition, not a summary of
	 * it — every entry below is here because of one of them, or because it was
	 * filed by hand. `+ assign` opens the unclaimed tags inline so a folder can
	 * be widened from the place you noticed it was too narrow, which is the
	 * whole reason that shortcut exists rather than a trip to mapping.
	 *
	 * The ruler and the fade at the bottom are the log's, deliberately: this is
	 * the same reading surface scoped to one folder, and it should not feel
	 * like a different screen. Its span and zoom persist under their own key,
	 * so scrolling around in a folder does not move the main log.
	 */
	import { page } from '$app/state';
	import EntryRow from '$lib/trophic/EntryRow.svelte';
	import FolderAssignMenu from '$lib/trophic/FolderAssignMenu.svelte';
	import TimelineNav from '$lib/trophic/TimelineNav.svelte';
	import { deviceType, handMode } from '$lib/trophic/device.svelte';
	import { todayKey } from '$lib/trophic/day';
	import { longpress } from '$lib/trophic/longpress';
	import type { ViewSpan } from '$lib/trophic/timeline-draw';
	import {
		assignEntry,
		getFolder,
		getFolders,
		getUnassignedTags,
		patchFolder,
		toggleLine,
		type Entry,
		type Folder,
		type FolderDetail,
		type UnassignedTag
	} from '$lib/trophic/api';

	const id = $derived(page.params.id!);

	let detail = $state<FolderDetail | null>(null);
	let folders = $state<Folder[]>([]);
	let unassigned = $state<UnassignedTag[]>([]);
	let error = $state<string | null>(null);
	let showAssign = $state(false);
	let isMobile = $state(false);
	let selectedDay = $state<string | null>(null);
	let viewSpan = $state<ViewSpan>('day');
	let menu = $state<{ x: number; y: number; entry: Entry } | null>(null);

	const today = todayKey();

	// The ruler follows the thumb on a phone, as it does on the log.
	const hand = handMode();
	const timelineRight = $derived(isMobile && hand.mode === 'right');

	async function refresh() {
		try {
			const [d, f, u] = await Promise.all([getFolder(id), getFolders(), getUnassignedTags()]);
			detail = d;
			folders = f.folders;
			unassigned = u.tags;
			// Open on the folder's most recent day rather than today: a folder
			// you have not written into this week is not an empty folder.
			if (!selectedDay && d.entries.length > 0) selectedDay = d.entries[0].day;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	$effect(() => {
		isMobile = deviceType().isMobile;
		refresh();
	});

	/** The ruler's density marks come from this folder alone. */
	const dates = $derived.by(() => {
		const counts: Record<string, number> = {};
		for (const e of detail?.entries ?? []) counts[e.day] = (counts[e.day] ?? 0) + 1;
		return counts;
	});

	const span = $derived.by(() => {
		if (!selectedDay) return null;
		if (viewSpan === 'day') return { start: selectedDay, end: selectedDay };
		const days = viewSpan === 'week' ? 7 : 30;
		const anchor = new Date(selectedDay + 'T00:00:00Z');
		anchor.setUTCDate(anchor.getUTCDate() - (days - 1));
		return { start: anchor.toISOString().slice(0, 10), end: selectedDay };
	});

	// Filtered in the browser, not refetched: the folder's entries are already
	// all here, and a folder is small enough that asking again would be slower
	// than looking.
	const visible = $derived(
		(detail?.entries ?? []).filter((e) => span && e.day >= span.start && e.day <= span.end)
	);

	const groups = $derived.by(() => {
		const map = new Map<string, Entry[]>();
		for (const e of visible) {
			if (!map.has(e.day)) map.set(e.day, []);
			map.get(e.day)!.push(e);
		}
		return [...map.entries()]
			.sort((a, b) => b[0].localeCompare(a[0]))
			.map(([day, list]) => ({ day, entries: list }));
	});

	function formatDateLabel(key: string): string {
		if (key === today) return 'today';
		const [y, m, d] = key.split('-').map(Number);
		return new Date(y, m - 1, d).toLocaleDateString(undefined, {
			weekday: 'short',
			month: 'short',
			day: 'numeric'
		});
	}

	async function act(work: Promise<unknown>) {
		error = null;
		try {
			await work;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		await refresh();
	}

	async function onToggle(entry: Entry, line: number) {
		try {
			const { entry: updated } = await toggleLine(entry.id, line);
			if (detail) {
				detail.entries = detail.entries.map((e) => (e.id === updated.id ? updated : e));
			}
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	const emptySpan = $derived(
		viewSpan === 'day' ? 'quiet day.' : viewSpan === 'week' ? 'quiet week.' : 'quiet month.'
	);
</script>

<header
	class="sticky top-0 z-40 flex items-center justify-between bg-[#14100c] px-6 py-5 text-[11px] tracking-wide text-stone-500"
>
	<a href="/log" class="transition-colors hover:text-stone-300">← folders</a>
	<span class="flex items-center gap-2 text-stone-300">
		{#if detail}
			<span class="h-2 w-2 shrink-0 rounded-full" style="background:{detail.folder.color}"></span>
			{detail.folder.name}
		{/if}
	</span>
	<a href="/" class="transition-colors hover:text-stone-300">capture →</a>
</header>

<main class="mx-auto flex w-full max-w-xl flex-1 flex-col gap-6 px-6 pb-20">
	{#if error}
		<p class="text-[11px] text-red-400">{error}</p>
	{/if}

	{#if detail}
		<!-- What defines the folder. -->
		<div class="flex flex-col gap-2">
			<div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px]">
				{#each detail.folder.tags as tag (tag)}
					<button
						type="button"
						class="text-blue-400/80 transition-colors hover:text-red-400"
						title="click to unassign"
						onclick={() => act(patchFolder(id, { remove_tags: [tag] }))}
					>
						{`<${tag}>`}
					</button>
				{:else}
					<span class="text-stone-500">no tags point here yet</span>
				{/each}
				<button
					type="button"
					class="ml-1 text-stone-500 transition-colors hover:text-stone-300"
					onclick={() => (showAssign = !showAssign)}
				>
					{showAssign ? 'done' : '+ assign'}
				</button>
			</div>

			{#if showAssign}
				<div
					class="mt-1 flex flex-wrap gap-3 rounded-lg border border-stone-800 bg-stone-900/40 p-3 text-[11px]"
				>
					{#each unassigned as tag (tag.tag)}
						<button
							type="button"
							class="text-blue-400 transition-colors hover:text-blue-200"
							onclick={() => act(patchFolder(id, { add_tags: [tag.tag] }))}
						>
							{`<${tag.tag}>`}<span class="ml-1 text-stone-600">×{tag.count}</span>
						</button>
					{:else}
						<span class="text-stone-500">no unassigned tags</span>
					{/each}
				</div>
			{/if}
		</div>

		<section class="flex flex-col gap-3">
			<div class="text-[10px] tracking-[0.15em] text-stone-500 uppercase">log</div>

			{#if detail.entries.length === 0}
				<p class="text-[11px] text-stone-500">
					nothing here yet — capture with these tags to fill it.
				</p>
			{:else}
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

				<div class="flex gap-3 {timelineRight ? 'flex-row-reverse' : ''}" style="height:320px">
					<TimelineNav
						{dates}
						selected={selectedDay}
						bind:viewSpan
						dense={isMobile}
						storageKey={id}
						onselect={(d) => (selectedDay = d)}
					/>
					<div class="relative flex-1">
						<div class="trophic-scrollbar-hide h-full overflow-y-auto">
							{#if visible.length > 0}
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
												<div
													class="py-0.5"
													use:longpress={(x, y) => (menu = { x, y, entry: e })}
												>
													<EntryRow entry={e} index={i} ontoggle={(line) => onToggle(e, line)} />
												</div>
											{/each}
										</div>
									{/each}
								</div>
							{:else}
								<p class="text-[11px] text-stone-500">{emptySpan}</p>
							{/if}
						</div>
						<div
							class="pointer-events-none absolute right-0 bottom-0 left-0 h-16"
							style="background:linear-gradient(to bottom, transparent, #14100c)"
						></div>
					</div>
				</div>
			{/if}
		</section>

		<!-- The folder's sentiment counts. A reading, not a verdict. -->
		{#if detail.sentiments.length > 0}
			{@const max = Math.max(...detail.sentiments.map((s) => s.count))}
			<div class="flex flex-col gap-1.5 text-[11px]">
				{#each detail.sentiments as s (s.name)}
					<div class="flex items-center gap-2" title="{s.count} entries here with \{s.name}">
						<span class="w-24 shrink-0 truncate text-right" style="color:#fb7185">{`\\${s.name}`}</span
						>
						<div class="h-[6px] flex-1 overflow-hidden rounded-full bg-stone-800">
							<div
								class="h-full rounded-full transition-all duration-500"
								style="width:{(s.count / max) * 100}%;background:#fb7185"
							></div>
						</div>
						<span class="w-6 shrink-0 text-right text-stone-500 tabular-nums">{s.count}</span>
					</div>
				{/each}
			</div>
		{/if}
	{/if}
</main>

{#if menu}
	{@const target = menu.entry}
	<FolderAssignMenu
		x={menu.x}
		y={menu.y}
		{folders}
		current={target.manual_folders[0] ?? null}
		onselect={(folderId) => act(assignEntry(target.id, folderId))}
		onclear={() => act(assignEntry(target.id, null))}
		onclose={() => (menu = null)}
	/>
{/if}
