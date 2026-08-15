<script lang="ts">
	/**
	 * Mapping — where a tag stops being loose and becomes part of a folder.
	 * Ported from `screens/MappingClient.tsx`.
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
		const file = (event.currentTarget as HTMLInputElement).files?.[0];
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
		(event.currentTarget as HTMLInputElement).value = '';
	}
</script>

<header
	class="sticky top-0 z-40 flex items-center justify-between bg-[#14100c] px-6 py-5 text-[11px] tracking-wide text-stone-500"
>
	<a href="/" class="transition-colors hover:text-stone-300">← capture</a>
	<span class="text-stone-300">mapping</span>
	<a href="/log" class="transition-colors hover:text-stone-300">folders →</a>
</header>

<main class="mx-auto flex w-full max-w-xl flex-1 flex-col gap-6 px-6 pb-20">
	{#if error}
		<p class="text-[11px] text-red-400">{error}</p>
	{/if}

	<section class="flex flex-col gap-3">
		<div class="text-[10px] tracking-[0.15em] text-stone-500 uppercase">
			unassigned · {unassigned.length}
		</div>

		{#if unassigned.length === 0}
			<p class="text-[11px] text-stone-500">nothing to assign. caught up.</p>
		{/if}

		<div class="flex flex-col">
			{#each unassigned as tag (tag.tag)}
				<div class="flex items-baseline justify-between gap-4 border-b border-stone-800 py-3">
					<span class="text-sm">
						<span style="color:#60a5fa">{`<${tag.tag}>`}</span>
						<span class="ml-2 text-[10px] text-stone-500">×{tag.count}</span>
					</span>

					{#if naming === tag.tag}
						<form
							class="flex items-baseline gap-2"
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
								class="w-32 border-b border-stone-700 bg-transparent py-1 text-[11px] text-stone-200 transition-colors focus:border-stone-500 focus:outline-none"
								style="caret-color:#e7e5e4"
								onkeydown={(e) => {
									if (e.key === 'Escape') naming = null;
								}}
							/>
							<button type="submit" class="text-[11px] text-stone-400 hover:text-stone-200">
								create
							</button>
						</form>
					{:else}
						<select
							value=""
							class="cursor-pointer bg-transparent text-[11px] text-stone-400 transition-colors hover:text-stone-200 focus:outline-none"
							style="color-scheme:dark"
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
	</section>

	{#if assignedFolders.length > 0}
		<section class="flex flex-col gap-4">
			<div class="text-[10px] tracking-[0.15em] text-stone-500 uppercase">assigned</div>
			{#each assignedFolders as f (f.id)}
				<div class="flex flex-col gap-1.5">
					<div class="flex items-center gap-2 text-xs text-stone-300">
						<span class="h-2 w-2 shrink-0 rounded-full" style="background:{f.color}"></span>
						<a href="/folders/{f.id}" class="hover:text-stone-100">{f.name}</a>
					</div>
					<div class="flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
						{#each f.tags as tag (tag)}
							<button
								type="button"
								class="text-blue-400/80 transition-colors hover:text-red-400"
								title="click to unassign"
								onclick={() => unassign(tag, f.id)}
							>
								{`<${tag}>`}
							</button>
						{/each}
					</div>
				</div>
			{/each}
		</section>
	{/if}

	<section class="flex flex-col gap-2 border-t border-stone-800 pt-5">
		<div class="text-[10px] tracking-[0.15em] text-stone-500 uppercase">import</div>
		<p class="text-[11px] leading-relaxed text-stone-500">
			a CSV of <span class="text-stone-400">time, text, tags, patterns</span>. Rows keep their own
			dates, and the tag columns are written back into the line — an imported entry is a line like
			any other.
		</p>
		<label class="flex items-baseline gap-3 text-[11px]">
			<span
				class="cursor-pointer rounded bg-stone-800 px-2.5 py-1 text-stone-400 transition-colors hover:bg-stone-700 hover:text-stone-200"
			>
				{importing ? 'reading…' : 'choose a file'}
				<input type="file" accept=".csv,text/csv" class="hidden" onchange={onFile} />
			</span>
			{#if imported}
				<span class="text-emerald-400">{imported}</span>
			{/if}
		</label>
	</section>
</main>
