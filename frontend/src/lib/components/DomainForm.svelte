<script lang="ts">
	import Dialog from './Dialog.svelte';
	import {
		accents,
		seasons,
		shapeBlurb,
		type DomainFields,
		type DomainShape,
		type DomainView,
		type SeasonFields,
		type SeasonState
	} from '$lib/api';

	interface Props {
		/** Omit to create; pass a domain to edit it. */
		domain?: DomainView | null;
		busy?: boolean;
		error?: string | null;
		onsubmit: (fields: DomainFields & { title: string }) => void;
		/** Season is a separate endpoint, so it saves on its own. */
		onseason?: (fields: SeasonFields) => void;
		oncancel: () => void;
		ondelete?: () => void;
	}

	let {
		domain = null,
		busy = false,
		error = null,
		onsubmit,
		onseason,
		oncancel,
		ondelete
	}: Props = $props();

	const SEASON_STATES: SeasonState[] = ['high', 'low', 'off'];

	let seasonUntil = $state(domain?.season.until ?? '');
	let seasonEndsOn = $state(domain?.season.ends_on ?? '');
	let seasonStrands = $state<string[]>(domain?.season.strands ?? []);

	const seasonDirty = $derived(
		!!domain &&
			(seasonUntil !== domain.season.until ||
				seasonEndsOn !== domain.season.ends_on ||
				seasonStrands.join(',') !== domain.season.strands.join(','))
	);

	function toggleSeasonStrand(name: string) {
		seasonStrands = seasonStrands.includes(name)
			? seasonStrands.filter((s) => s !== name)
			: [...seasonStrands, name];
	}

	const editing = !!domain;

	let title = $state(domain?.title ?? '');
	let priority = $state(domain?.priority ?? 100);
	let color = $state(domain?.color ?? 'amber');
	let shape = $state<DomainShape>(domain?.shape ?? 'ladder');
	let cadence = $state(domain?.cadence ?? 'daily');
	let cadenceN = $state(domain?.cadence_n ?? 3);
	let strandsText = $state((domain?.strands ?? []).join(', '));

	const strands = $derived(
		strandsText
			.split(',')
			.map((s) => s.trim())
			.filter(Boolean)
	);

	const SHAPES: { key: DomainShape; when: string }[] = [
		{ key: 'ladder', when: 'Levels that genuinely nest, like HSK. One active node.' },
		{
			key: 'strands',
			when: 'Tracks that must advance together, like Berklee running harmony, ear and technique in the same semester. One active node per strand.'
		},
		{
			key: 'cycles',
			when: 'Repeated whole projects with craft feeding them, like AFI cycle films. The current project plus what it waits on.'
		}
	];

	// Changing an existing domain to `strands` migrates every unassigned node
	// into the first strand — say so, rather than surprising them after the save.
	const willMigrate = $derived(
		editing && shape === 'strands' && domain!.shape !== 'strands' && strands.length > 0
	);
	const willClear = $derived(editing && shape !== 'strands' && domain!.shape === 'strands');

	function submit() {
		const fields: DomainFields & { title: string } = {
			title: title.trim(),
			priority: Number(priority),
			color,
			shape,
			cadence,
			cadence_n: Number(cadenceN)
		};
		if (shape === 'strands') fields.strands = strands;
		onsubmit(fields);
	}

	const invalid = $derived(!title.trim() || (shape === 'strands' && strands.length === 0));
</script>

<Dialog
	title={editing ? `Edit ${domain!.title}` : 'New domain'}
	subtitle={editing ? domain!.source : 'Shape decides how many nodes are active at once.'}
	submitLabel={editing ? 'save' : 'create domain'}
	{busy}
	{error}
	onsubmit={submit}
	oncancel={oncancel}
>
	<label class="block">
		<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Title</span>
		<!-- svelte-ignore a11y_autofocus -->
		<input
			bind:value={title}
			autofocus={!editing}
			placeholder="Electric Guitar"
			class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 placeholder:text-stone-700 focus:border-amber-500/60 focus:outline-none"
		/>
	</label>

	<div>
		<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Shape</span>
		<div class="mt-1.5 space-y-1">
			{#each SHAPES as s (s.key)}
				<button
					type="button"
					onclick={() => (shape = s.key)}
					class="block w-full rounded-sm border px-3 py-2 text-left transition
					{shape === s.key
						? 'border-amber-500/70 bg-amber-500/10'
						: 'border-stone-800 hover:border-stone-600'}"
				>
					<span
						class="text-[11px] tracking-[0.16em] uppercase {shape === s.key
							? 'text-amber-300'
							: 'text-stone-400'}"
					>
						{s.key}
					</span>
					<span class="ml-2 text-[10px] text-stone-600">{shapeBlurb[s.key]}</span>
					<p class="mt-0.5 text-[11px] text-stone-500">{s.when}</p>
				</button>
			{/each}
		</div>
	</div>

	{#if shape === 'strands'}
		<label class="block">
			<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Strands</span>
			<input
				bind:value={strandsText}
				placeholder="technique, theory, ear"
				class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 placeholder:text-stone-700 focus:border-amber-500/60 focus:outline-none"
			/>
			<p class="mt-1 text-[11px] text-stone-500">
				Comma-separated, in display order. Every node must belong to one.
			</p>
			{#if willMigrate}
				<p class="mt-1.5 rounded-sm border border-amber-600/40 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-200">
					All {domain!.total_nodes} existing nodes will be moved into
					<span class="font-mono">{strands[0]}</span>. Reassign them per-node afterwards.
				</p>
			{/if}
		</label>
	{:else if willClear}
		<p class="rounded-sm border border-amber-600/40 bg-amber-500/10 px-2 py-1.5 text-[11px] text-amber-200">
			Leaving <span class="font-mono">strands</span> clears the strand on all
			{domain!.total_nodes} nodes.
		</p>
	{/if}

	<div class="grid grid-cols-2 gap-3">
		<label class="block">
			<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Priority</span>
			<input
				type="number"
				bind:value={priority}
				class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
			/>
			<p class="mt-1 text-[11px] text-stone-500">Lower sorts higher. This is the ranking.</p>
		</label>
		<label class="block">
			<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Cadence</span>
			<select
				bind:value={cadence}
				class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
			>
				<option value="daily">every day</option>
				<option value="weekdays">weekdays</option>
				<option value="every_n_days">every N days</option>
			</select>
			{#if cadence === 'every_n_days'}
				<input
					type="number"
					min="1"
					bind:value={cadenceN}
					class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
				/>
			{/if}
		</label>
	</div>

	<div>
		<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Colour</span>
		<div class="mt-1.5 flex gap-1.5">
			{#each Object.keys(accents) as name (name)}
				<button
					type="button"
					onclick={() => (color = name)}
					aria-label={name}
					class="h-7 flex-1 rounded-sm border transition {accents[name].bg}
					{color === name ? 'border-stone-200 opacity-100' : 'border-transparent opacity-40 hover:opacity-70'}"
				></button>
			{/each}
		</div>
	</div>

	{#if editing && domain && onseason}
		<div class="border-t border-stone-800 pt-4">
			<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Season</span>
			<p class="mt-1 mb-2 text-[11px] text-stone-500">
				Whether this domain is acquiring or only being kept alive. Saves on its own,
				separately from the rest of this form.
			</p>

			<div class="flex gap-1.5">
				{#each SEASON_STATES as s (s)}
					{@const blocked = s === 'off' && !domain.season.can_park}
					<button
						type="button"
						disabled={busy || blocked}
						onclick={() => onseason?.({ state: s })}
						title={blocked
							? `${domain.season.decaying_count} nodes here decay — parking them means coming back to a wall of maintenance. Use holding.`
							: seasons[s].hint}
						class="flex-1 rounded-sm border px-2 py-1.5 text-[10px] tracking-[0.16em] uppercase transition disabled:cursor-not-allowed disabled:opacity-25
						{domain.season.state === s
							? seasons[s].tone
							: 'border-stone-800 text-stone-500 hover:border-stone-700'}"
					>
						{seasons[s].label}
					</button>
				{/each}
			</div>
			<p class="mt-1.5 text-[10px] text-stone-600">{seasons[domain.season.state].hint}</p>

			{#if !domain.season.can_park}
				<p class="mt-1 text-[10px] text-stone-600">
					<span class="font-mono">{domain.season.decaying_count}</span> nodes here decay, so this
					domain can be held but never parked.
				</p>
			{/if}

			{#if shape === 'strands' && domain.season.state === 'high'}
				<div class="mt-3">
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">
						Width — strands acquiring
					</span>
					<div class="mt-1.5 flex flex-wrap gap-1.5">
						{#each domain.strands as name (name)}
							<button
								type="button"
								onclick={() => toggleSeasonStrand(name)}
								class="rounded-sm border px-2 py-1 font-mono text-[10px] transition
								{seasonStrands.includes(name) || !seasonStrands.length
									? 'border-emerald-500/50 text-emerald-300'
									: 'border-stone-800 text-stone-600 hover:border-stone-700'}"
							>
								{name}
							</button>
						{/each}
					</div>
					<p class="mt-1 text-[10px] text-stone-600">
						{seasonStrands.length
							? `${seasonStrands.length} of ${domain.strands.length} acquiring.`
							: 'None selected — all strands acquire, which is the expensive default.'}
					</p>
				</div>
			{/if}

			<div class="mt-3 grid grid-cols-2 gap-3">
				<label class="block">
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Ends on date</span>
					<input
						type="date"
						bind:value={seasonUntil}
						class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
					/>
				</label>
				<label class="block">
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">…or when this ships</span>
					<select
						bind:value={seasonEndsOn}
						class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
					>
						<option value="">nothing</option>
						{#each domain.nodes as n (n.id)}
							<option value={n.id}>{n.title}</option>
						{/each}
					</select>
				</label>
			</div>
			<p class="mt-1 text-[10px] text-stone-600">
				Both, ideally. A trigger alone deadlocks when the project stalls; a date alone
				throws away the reward for shipping early. Whichever lands first ends it.
			</p>

			<button
				type="button"
				disabled={busy || !seasonDirty}
				onclick={() =>
					onseason?.({ until: seasonUntil, ends_on: seasonEndsOn, strands: seasonStrands })}
				class="mt-2 w-full rounded-sm border border-stone-700 py-1.5 text-[10px] tracking-[0.16em] text-stone-300 uppercase hover:border-stone-600 disabled:opacity-25"
			>
				save season
			</button>
		</div>
	{/if}

	{#if invalid}
		<p class="text-[11px] text-stone-600">
			{!title.trim() ? 'A title is required.' : 'A strands domain needs at least one strand.'}
		</p>
	{/if}

	{#if editing && ondelete}
		<div class="flex items-center justify-between gap-3 border-t border-black/50 pt-3.5">
			<p class="font-mono text-[10px] text-stone-600">
				writes {domain!.source} — comments in that file are not preserved
			</p>
			<button
				type="button"
				onclick={ondelete}
				class="shrink-0 rounded-sm border border-rose-900/60 px-3 py-1.5 text-[11px] tracking-[0.16em] text-rose-400/80 uppercase hover:bg-rose-500/10"
			>
				delete domain
			</button>
		</div>
	{/if}
</Dialog>
