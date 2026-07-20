<script lang="ts">
	import Dialog from './Dialog.svelte';
	import { kinds, roman, type DomainView, type NodeFields, type NodeKind } from '$lib/api';

	interface Props {
		domain: DomainView;
		/** Prefilled tier when adding from a tier column's foot. */
		tier?: number;
		busy?: boolean;
		error?: string | null;
		onsubmit: (fields: NodeFields & { title: string }) => void;
		oncancel: () => void;
	}

	let { domain, tier = 1, busy = false, error = null, onsubmit, oncancel }: Props = $props();

	let title = $state('');
	let kind = $state<NodeKind>('drill');
	let strand = $state(domain.strands[0] ?? '');
	let nodeTier = $state(tier);
	let estimate = $state(10);
	let minEach = $state('');
	let gate = $state('');
	let entryText = $state('');
	let note = $state('');
	let phasesText = $state('prep, do it, finish');
	let scheduled = $state('');
	let decayDays = $state(0);
	let metric = $state('');
	let metricTarget = $state(0);

	const isProject = $derived(kind === 'project');
	const meta = $derived(kinds[kind]);

	const phases = $derived(
		phasesText
			.split(',')
			.map((p) => p.trim())
			.filter(Boolean)
	);

	// Phases are comma-separated because they are short; entry lines are
	// sentences, so they split on newlines instead.
	const entry = $derived(
		entryText
			.split('\n')
			.map((line) => line.trim())
			.filter(Boolean)
	);

	function submit() {
		const fields: NodeFields & { title: string } = {
			title: title.trim(),
			tier: Number(nodeTier),
			kind,
			min_each: minEach.trim(),
			gate: gate.trim(),
			entry,
			note: note.trim()
		};
		if (domain.shape === 'strands') fields.strand = strand;
		if (isProject) {
			fields.phases = phases;
		} else {
			fields.estimate = Math.max(1, Number(estimate));
		}
		if (kind === 'drill' && Number(decayDays) > 0) fields.decay_days = Number(decayDays);
		if (kind === 'exam' && scheduled.trim()) fields.scheduled = scheduled.trim();
		if (metric.trim()) {
			fields.metric = metric.trim();
			if (Number(metricTarget) > 0) fields.metric_target = Number(metricTarget);
		}
		onsubmit(fields);
	}

	const invalid = $derived(!title.trim() || (isProject && phases.length === 0));
</script>

<Dialog
	title="New node · tier {roman(nodeTier)}"
	subtitle="The id is slugged from the title and never changes — every log entry references it."
	submitLabel="create node"
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
			autofocus
			placeholder="What is this node?"
			class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 placeholder:text-stone-700 focus:border-amber-500/60 focus:outline-none"
		/>
	</label>

	<div>
		<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Kind</span>
		<div class="mt-1.5 grid grid-cols-5 gap-1">
			{#each Object.entries(kinds) as [key, k] (key)}
				<button
					type="button"
					onclick={() => (kind = key as NodeKind)}
					title={k.hint}
					class="rounded-sm border px-1 py-1.5 text-[10px] tracking-wide uppercase transition
					{kind === key
						? 'border-amber-500/70 bg-amber-500/10 text-amber-300'
						: 'border-stone-800 text-stone-500 hover:border-stone-600 hover:text-stone-300'}"
				>
					{k.label}
				</button>
			{/each}
		</div>
		<p class="mt-1.5 text-[11px] text-stone-500">{meta.hint}</p>
	</div>

	<div class="grid grid-cols-2 gap-3">
		<label class="block">
			<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Tier</span>
			<input
				type="number"
				min="1"
				max="40"
				bind:value={nodeTier}
				class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
			/>
		</label>

		{#if domain.shape === 'strands'}
			<label class="block">
				<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Strand</span>
				<select
					bind:value={strand}
					class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
				>
					{#each domain.strands as s (s)}
						<option value={s}>{s}</option>
					{/each}
				</select>
			</label>
		{:else if !isProject}
			<label class="block">
				<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">
					Estimated {meta.unit}
				</span>
				<input
					type="number"
					min="1"
					bind:value={estimate}
					class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
				/>
			</label>
		{/if}
	</div>

	{#if isProject}
		<!-- A project has no session target at all. Phases replace it entirely. -->
		<label class="block">
			<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Phases</span>
			<input
				bind:value={phasesText}
				placeholder="prep, shoot, post"
				class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 placeholder:text-stone-700 focus:border-amber-500/60 focus:outline-none"
			/>
			<p class="mt-1 text-[11px] text-stone-500">
				Comma-separated. A project accrues phases, not days — there is no session
				count, because you cannot do 12% of a shoot day.
			</p>
			{#if phases.length}
				<p class="mt-1 font-mono text-[10px] text-stone-600">
					{phases.length} phases: {phases.join(' · ')}
				</p>
			{/if}
		</label>
	{:else if domain.shape === 'strands'}
		<label class="block">
			<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">
					Estimated {meta.unit}
				</span>
			<input
				type="number"
				min="1"
				bind:value={estimate}
				class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
			/>
		</label>
	{/if}

	{#if kind === 'exam'}
		<label class="block">
			<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Scheduled</span>
			<input
				type="date"
				bind:value={scheduled}
				class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
			/>
			<p class="mt-1 text-[11px] text-stone-500">
				Optional — leave blank until you register, and the card will say so.
			</p>
		</label>
	{/if}

	{#if kind === 'drill'}
		<label class="block">
			<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Decay days</span>
			<input
				type="number"
				min="0"
				bind:value={decayDays}
				class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
			/>
			<p class="mt-1 text-[11px] text-stone-500">
				0 = never goes stale. Otherwise a completed node returns to
				<span class="text-amber-500">maintenance</span> after this many idle days.
			</p>
		</label>
	{/if}

	{#if !isProject}
		<div class="grid grid-cols-2 gap-3">
			<label class="block">
				<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Metric</span>
				<input
					bind:value={metric}
					placeholder="bpm"
					class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 placeholder:text-stone-700 focus:border-amber-500/60 focus:outline-none"
				/>
			</label>
			<label class="block">
				<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Target</span>
				<input
					type="number"
					min="0"
					bind:value={metricTarget}
					disabled={!metric.trim()}
					class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none disabled:opacity-40"
				/>
			</label>
		</div>
		<p class="-mt-2 text-[11px] text-stone-500">
			Optional. If set, each check-off can carry a number you type. Stored and
			charted, never interpreted.
		</p>
	{/if}

	<label class="block">
		<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">
			{isProject ? 'Per working session' : 'Minimum each time'}
		</span>
		<input
			bind:value={minEach}
			placeholder={isProject ? 'one working day' : '25 min'}
			class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 placeholder:text-stone-700 focus:border-amber-500/60 focus:outline-none"
		/>
	</label>

	<label class="block">
		<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Gate</span>
		<textarea
			bind:value={gate}
			rows="2"
			placeholder="What does done actually mean? Never parsed — you decide when it's true."
			class="mt-1 w-full resize-none rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 placeholder:text-stone-700 focus:border-amber-500/60 focus:outline-none"
		></textarea>
	</label>

	<label class="block">
		<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">
			Entry — how to start
		</span>
		<textarea
			bind:value={entryText}
			rows="3"
			placeholder={'One per line. Book, course, or search term — whatever gets you to session one.'}
			class="mt-1 w-full resize-y rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 placeholder:text-stone-700 focus:border-amber-500/60 focus:outline-none"
		></textarea>
	</label>

	{#if invalid}
		<p class="text-[11px] text-stone-600">
			{!title.trim() ? 'A title is required.' : 'A project needs at least one phase.'}
		</p>
	{/if}
</Dialog>
