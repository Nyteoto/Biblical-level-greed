<script lang="ts">
	/**
	 * Mapping — where a tag stops being loose and becomes part of a folder.
	 * Ported from `screens/MappingClient.tsx`.
	 *
	 * It is no longer a tab. Settings shows the mapping at a glance and the one
	 * number that ever needs acting on — how many tags point nowhere — and this
	 * is where that link lands. `--assign` in the capture bar still opens it.
	 *
	 * The screen is two lists and one gesture. On the left of the divide are
	 * the tags nothing has claimed, commonest first, because the one you have
	 * written forty times is the one worth filing. On the right is where each
	 * claimed tag went, and clicking it lets go again.
	 *
	 * Everything here is retroactive and nothing here is destructive: mapping
	 * `<deploy>` to Work pulls every entry ever written with `<deploy>` in it
	 * into Work, and unmapping pushes them back out, because membership is
	 * resolved from this mapping rather than copied out of it. That is the one
	 * property worth protecting if this screen is ever rebuilt.
	 *
	 * The source asks for a new folder's name with `prompt()`. This asks with
	 * an input on the row, which is the same interaction without handing the
	 * window over to the platform mid-gesture.
	 */
	import TabPill from '$lib/trophic/TabPill.svelte';
	import { SYNTAX_COLORS } from '$lib/trophic/colors';
	import {
		createFolder,
		getFolders,
		getUnassignedTags,
		importCsv,
		patchFolder,
		type Folder,
		type UnassignedTag
	} from '$lib/trophic/api';

	let folders = $state<Folder[]>([]);
	let unassigned = $state<UnassignedTag[]>([]);
	let error = $state<string | null>(null);
	/** The tag whose row has opened an input for a brand-new folder. */
	let naming = $state<string | null>(null);
	let newName = $state('');

	async function refresh() {
		try {
			const [f, u] = await Promise.all([getFolders(), getUnassignedTags()]);
			folders = f.folders;
			unassigned = u.tags;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
	}

	$effect(() => {
		refresh();
	});

	async function act(work: Promise<unknown>) {
		error = null;
		try {
			await work;
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		// Always re-read. The optimistic updates the source does are worth it
		// over a network; over a loopback socket they only add a way to be
		// wrong about what the server did.
		await refresh();
	}

	function assign(tag: string, folderId: string) {
		act(patchFolder(folderId, { add_tags: [tag] }));
	}

	function unassign(tag: string, folderId: string) {
		act(patchFolder(folderId, { remove_tags: [tag] }));
	}

	async function createAndAssign(tag: string) {
		const name = newName.trim();
		if (!name) return;
		naming = null;
		newName = '';
		await act(createFolder(name, [tag]));
	}

	const assignedFolders = $derived(folders.filter((f) => f.tags.length > 0));

	// Import lands here rather than on a vault screen of its own: the source's
	// is wrapped around encryption setup, which this port does not have, and
	// what is left is one file input. This is already the housekeeping screen.
	let importing = $state(false);
	let imported = $state<string | null>(null);

	async function onFile(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		if (!file) return;
		importing = true;
		imported = null;
		error = null;
		try {
			const result = await importCsv(await file.text());
			imported = `imported ${result.imported}${
				result.skipped ? `, skipped ${result.skipped} too long` : ''
			}`;
			await refresh();
		} catch (e) {
			error = e instanceof Error ? e.message : String(e);
		}
		importing = false;
		// Let the same file be chosen again after a fix.
		input.value = '';
	}
</script>

<div class="flex min-h-dvh flex-col">
	<div class="flex shrink-0 items-center justify-between px-[34px] pt-[22px]">
		<TabPill />
		<a href="/settings" class="text-[13px] font-semibold text-neutral-700 hover:text-ink">
			← Settings
		</a>
	</div>

	<main class="mx-auto flex w-full max-w-[860px] flex-1 flex-col gap-[26px] px-[34px] pt-[26px] pb-16">
		<div>
			<div class="text-[10px] font-bold tracking-[0.22em] text-accent-700 uppercase">
				Point nowhere
			</div>
			<div class="mt-2 flex items-baseline gap-4">
				<h1 class="text-[52px] leading-[0.95] font-extrabold tracking-[-0.035em]">
					{unassigned.length}
				</h1>
				<span class="text-[13px] text-neutral-700">
					{unassigned.length === 1 ? 'tag has' : 'tags have'} been written and never filed. Mapping
					one is retroactive: every entry that ever carried it joins the folder.
				</span>
			</div>
		</div>

		{#if error}
			<p class="text-[12px] text-accent-700">{error}</p>
		{/if}

		{#if unassigned.length > 0}
			<div class="rounded-[16px] bg-surface px-[18px] py-2 shadow-md">
				{#each unassigned as tag (tag.tag)}
					<div class="flex items-center gap-4 py-3">
						<span class="font-mono text-[14px]" style="color:{SYNTAX_COLORS.folder}">
							{`<${tag.tag}>`}
						</span>
						<span class="text-[12px] text-neutral-700 tabular-nums">×{tag.count}</span>
						<span class="flex-1"></span>

						{#if naming === tag.tag}
							<form
								class="flex items-center gap-2"
								onsubmit={(e) => {
									e.preventDefault();
									createAndAssign(tag.tag);
								}}
							>
								<!-- svelte-ignore a11y_autofocus -->
								<input
									autofocus
									bind:value={newName}
									placeholder="folder name"
									class="w-40 rounded-lg bg-neutral-200 px-3 py-1.5 text-[13px] focus:outline-none"
									onkeydown={(e) => {
										if (e.key === 'Escape') naming = null;
									}}
								/>
								<button type="submit" class="text-[13px] font-semibold">create</button>
							</form>
						{:else}
							<select
								value=""
								class="cursor-pointer rounded-lg bg-neutral-200 px-3 py-1.5 text-[13px] font-semibold focus:outline-none"
								onchange={(e) => {
									const value = e.currentTarget.value;
									e.currentTarget.value = '';
									if (value === '__new__') {
										newName = '';
										naming = tag.tag;
									} else if (value) {
										assign(tag.tag, value);
									}
								}}
							>
								<option value="" disabled>→ folder</option>
								{#each folders as f (f.id)}
									<option value={f.id}>{f.name}</option>
								{/each}
								<option value="__new__">+ new folder…</option>
							</select>
						{/if}
					</div>
				{/each}
			</div>
		{:else}
			<p class="text-[13px] text-neutral-700">nothing to assign. caught up.</p>
		{/if}

		{#if assignedFolders.length > 0}
			<div>
				<div class="text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">
					Where the rest went
				</div>
				<div class="mt-2.5 rounded-[16px] bg-surface px-[18px] py-2 shadow-md">
					{#each assignedFolders as f (f.id)}
						<div class="flex items-baseline gap-3 py-3">
							<span
								class="h-2 w-2 shrink-0 translate-y-[-2px] rounded-full"
								style="background:{f.color}"
							></span>
							<a href="/folders/{f.id}" class="shrink-0 text-[14px] font-semibold">{f.name}</a>
							<div class="flex flex-1 flex-wrap justify-end gap-x-3 gap-y-1">
								{#each f.tags as tag (tag)}
									<button
										type="button"
										class="font-mono text-[12px] transition-colors hover:text-accent-700"
										style="color:{f.color}"
										title="click to unmap — the entries stay, they just leave this folder"
										onclick={() => unassign(tag, f.id)}
									>
										{`<${tag}>`}
									</button>
								{/each}
							</div>
						</div>
					{/each}
				</div>
			</div>
		{/if}

		<div>
			<div class="text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">Import</div>
			<div class="mt-2.5 flex flex-col gap-3 rounded-[16px] bg-surface px-[18px] py-4 shadow-md">
				<p class="text-[13px] leading-[1.5] text-neutral-700">
					A CSV of <span class="font-mono text-neutral-800">time, text, tags, patterns</span>. Rows
					keep their own dates, and the tag columns are written back into the line — an imported
					entry is a line like any other.
				</p>
				<label class="flex items-center gap-3 text-[13px]">
					<span
						class="lift lift-sm cursor-pointer rounded-[11px] bg-surface px-4 py-2.5 font-semibold shadow-sm"
					>
						{importing ? 'reading…' : 'Choose a file'}
						<input type="file" accept=".csv,text/csv" class="hidden" onchange={onFile} />
					</span>
					{#if imported}
						<span class="text-neutral-800">{imported}</span>
					{/if}
				</label>
			</div>
		</div>
	</main>
</div>
