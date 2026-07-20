<script lang="ts">
	import {
		addJournal,
		deleteNode,
		disconnectNodes,
		kinds,
		patchNode,
		reorderNode,
		roman,
		toggleComplete,
		togglePhase,
		toggleSession,
		type NodeKind,
		type TreeNode
	} from '$lib/api';

	interface Props {
		domainId: string;
		node: TreeNode;
		nodes: TreeNode[];
		/** The domain's declared strands; empty unless its shape is `strands`. */
		strands?: string[];
		onchange: () => Promise<void> | void;
		onclose: () => void;
	}

	let { domainId, node, nodes, strands = [], onchange, onclose }: Props = $props();

	let tab = $state<'params' | 'journal'>('params');
	let busy = $state(false);
	let error = $state<string | null>(null);
	// Renamed from `entry` when the node schema gained an `entry` field of its
	// own — this one is the journal composer, which is a different thing.
	let journalDraft = $state('');

	// Local copy so typing doesn't fight the server; reset when the node changes.
	let draft = $state({ ...node });
	// `entry` is a list, but one-per-line in a textarea is the only editing shape
	// that stays honest to how it reads on the card.
	let entryDraft = $state(node.entry.join('\n'));
	let editingId = $state(node.id);
	$effect(() => {
		if (node.id !== editingId) {
			editingId = node.id;
			draft = { ...node };
			entryDraft = node.entry.join('\n');
			tab = 'params';
			error = null;
		}
	});

	const entryLines = (text: string) =>
		text
			.split('\n')
			.map((line) => line.trim())
			.filter(Boolean);

	const dirty = $derived(
		draft.title !== node.title ||
			Number(draft.tier) !== node.tier ||
			Number(draft.estimate) !== node.estimate ||
			draft.min_each !== node.min_each ||
			draft.gate !== node.gate ||
			draft.note !== node.note ||
			draft.metric !== node.metric ||
			Number(draft.metric_target) !== node.metric_target ||
			Number(draft.decay_days) !== node.decay_days ||
			draft.scheduled !== node.scheduled ||
			entryLines(entryDraft).join('\n') !== node.entry.join('\n')
	);

	const titleOf = (id: string) => nodes.find((n) => n.id === id)?.title ?? id;

	// A measurable gate stores the number you typed alongside today's check-off.
	let metricInput = $state('');

	// Turning a node into a project needs phases, because a project has no
	// session count to fall back on. Ask for them inline rather than failing.
	let needPhasesFor = $state<NodeKind | null>(null);
	let phasesDraft = $state('');

	function changeKind(next: NodeKind) {
		if (next === node.kind) return;
		if (next === 'project' && !node.phases.length) {
			needPhasesFor = next;
			phasesDraft = 'prep, do it, finish';
			return;
		}
		return run(() => patchNode(domainId, node.id, { kind: next }));
	}

	function confirmPhases() {
		const phases = phasesDraft
			.split(',')
			.map((p) => p.trim())
			.filter(Boolean);
		if (!phases.length) return;
		needPhasesFor = null;
		return run(() => patchNode(domainId, node.id, { kind: 'project', phases }));
	}

	function checkOff() {
		const raw = metricInput.trim();
		const value = raw === '' ? undefined : Number(raw);
		metricInput = '';
		return toggleSession(
			domainId,
			node.id,
			undefined,
			Number.isFinite(value as number) ? (value as number) : undefined
		);
	}

	async function run(fn: () => Promise<unknown>) {
		if (busy) return;
		busy = true;
		error = null;
		try {
			await fn();
			await onchange();
		} catch (e) {
			error = (e as Error).message.replace(/^\d+ [^:]+: /, '');
		} finally {
			busy = false;
		}
	}

	const save = () =>
		run(() =>
			patchNode(domainId, node.id, {
				title: draft.title,
				tier: Number(draft.tier),
				estimate: Number(draft.estimate),
				metric: draft.metric,
				metric_target: Number(draft.metric_target),
				decay_days: Number(draft.decay_days),
				scheduled: draft.scheduled,
				min_each: draft.min_each,
				gate: draft.gate,
				entry: entryLines(entryDraft),
				note: draft.note
			})
		);

	const remove = () =>
		run(async () => {
			await deleteNode(domainId, node.id);
			onclose();
		});

	const post = () =>
		run(async () => {
			const text = journalDraft.trim();
			if (!text) return;
			await addJournal(domainId, node.id, text);
			journalDraft = '';
		});
</script>

<aside
	class="flex w-[340px] shrink-0 flex-col border-l border-black/60 bg-[#171310]"
	aria-label="Node details"
>
	<header class="border-b border-black/50 px-4 py-3">
		<div class="flex items-start justify-between gap-3">
			<div class="min-w-0">
				<div class="flex items-center gap-2">
					<span
						class="rounded-sm border border-amber-500/40 bg-black/40 px-1.5 py-0.5 font-mono text-[10px] text-amber-400"
					>
						{roman(node.tier)}
					</span>
					<span class="text-[10px] tracking-[0.18em] text-stone-500 uppercase">
						{node.status}
					</span>
					<span
						class="rounded-sm border border-stone-800 px-1.5 py-px font-mono text-[9px] tracking-wider text-stone-500 uppercase"
						title={kinds[node.kind].hint}
					>
						{node.kind}
					</span>
					{#if node.strand}
						<span class="font-mono text-[9px] text-stone-600">{node.strand}</span>
					{/if}
				</div>
				<h2 class="mt-1.5 truncate text-sm font-medium text-stone-100">{node.title}</h2>
				<p
					class="mt-0.5 font-mono text-[10px] text-stone-600"
					title="Fixed at creation — the log references this id"
				>
					{node.id}
				</p>
			</div>
			<button onclick={onclose} class="text-stone-600 hover:text-stone-300" aria-label="Close">
				✕
			</button>
		</div>

		{#if node.status === 'open' && node.waiting_on.length}
			<!-- Advice, not a block. A soft edge never disables the buttons below. -->
			<p class="mt-2 rounded-sm border border-dashed border-stone-700 px-2 py-1.5 text-[11px] text-stone-400">
				usually after {node.waiting_on.map(titleOf).join(', ')} — nothing stops you starting now
			</p>
		{/if}

		{#if node.kind === 'project'}
			<!-- A project has no daily check-off. It has phases. -->
			<div class="mt-3 flex flex-wrap gap-1.5">
				{#each node.phases as phase (phase)}
					{@const done = node.phases_done.includes(phase)}
					<button
						onclick={() => run(() => togglePhase(domainId, node.id, phase))}
						disabled={busy}
						class="rounded-sm border px-2 py-1 text-[11px] transition disabled:opacity-40
						{done
							? 'border-amber-500/60 bg-black/30 text-amber-300'
							: 'border-stone-700 text-stone-500 hover:border-stone-600 hover:text-stone-300'}"
					>
						{done ? '☑' : '☐'}
						{phase}
					</button>
				{/each}
			</div>
		{/if}

		<div class="mt-3 flex gap-1.5">
			{#if node.kind !== 'project'}
				{#if node.metric}
					<input
						bind:value={metricInput}
						type="number"
						inputmode="numeric"
						placeholder={node.metric}
						aria-label="{node.metric} reached today"
						class="w-16 rounded-sm border border-stone-800 bg-black/40 px-1.5 py-1.5 text-center font-mono text-[11px] text-stone-200 placeholder:text-stone-700 focus:border-stone-600 focus:outline-none"
					/>
				{/if}
				<button
					onclick={() => run(() => checkOff())}
					disabled={busy || node.status === 'locked' || node.status === 'done'}
					class="flex-1 rounded-sm border px-2 py-1.5 text-[11px] tracking-wide uppercase transition disabled:opacity-30
					{node.checked_today
						? 'border-stone-700 text-stone-400'
						: 'border-amber-500/60 text-amber-300 hover:bg-amber-500/10'}"
				>
					{node.checked_today ? 'undo today' : node.kind === 'social' ? 'log one' : 'check off'}
				</button>
			{/if}
			<button
				onclick={() => run(() => toggleComplete(domainId, node.id))}
				disabled={busy || node.status === 'locked'}
				class="flex-1 rounded-sm border px-2 py-1.5 text-[11px] tracking-wide uppercase transition disabled:opacity-30
				{node.status === 'done'
					? 'border-stone-700 text-stone-400'
					: node.ready_to_complete
						? 'border-emerald-500/60 text-emerald-300 hover:bg-emerald-500/10'
						: 'border-stone-700 text-stone-500 hover:border-stone-600'}"
			>
				{node.status === 'done' ? 'reopen' : 'complete'}
			</button>
		</div>
	</header>

	<nav class="flex border-b border-black/50 text-[11px] tracking-[0.16em] uppercase">
		{#each ['params', 'journal'] as name}
			<button
				onclick={() => (tab = name as typeof tab)}
				class="flex-1 py-2 transition {tab === name
					? 'border-b-2 border-amber-400/80 text-amber-300'
					: 'text-stone-500 hover:text-stone-300'}"
			>
				{name}{name === 'journal' && node.journal.length ? ` (${node.journal.length})` : ''}
			</button>
		{/each}
	</nav>

	{#if error}
		<p class="border-b border-rose-500/30 bg-rose-500/10 px-4 py-2 text-[11px] text-rose-200">
			{error}
		</p>
	{/if}

	<div class="flex-1 overflow-y-auto p-4">
		{#if tab === 'params'}
			<div class="space-y-3.5">
				<label class="block">
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Title</span>
					<input
						type="text"
						bind:value={draft.title}
						class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
					/>
				</label>

				<div>
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Kind</span>
					<div class="mt-1.5 grid grid-cols-5 gap-1">
						{#each Object.entries(kinds) as [key, k] (key)}
							<button
								type="button"
								onclick={() => changeKind(key as NodeKind)}
								disabled={busy}
								title={k.hint}
								class="rounded-sm border px-1 py-1.5 text-[10px] tracking-wide uppercase transition disabled:opacity-40
								{node.kind === key
									? 'border-amber-500/70 bg-amber-500/10 text-amber-300'
									: 'border-stone-800 text-stone-500 hover:border-stone-600 hover:text-stone-300'}"
							>
								{k.label}
							</button>
						{/each}
					</div>
					<p class="mt-1.5 text-[11px] text-stone-500">{kinds[node.kind].hint}</p>

					{#if needPhasesFor}
						<div class="mt-2 rounded-sm border border-amber-600/40 bg-amber-500/5 p-2">
							<p class="text-[11px] text-amber-200">
								A project accrues phases, not days. Name them to convert — the
								session count will be dropped.
							</p>
							<div class="mt-1.5 flex gap-1.5">
								<input
									bind:value={phasesDraft}
									placeholder="prep, shoot, post"
									class="min-w-0 flex-1 rounded-sm border border-stone-800 bg-black/40 px-2 py-1 text-[12px] text-stone-100 placeholder:text-stone-700 focus:border-amber-500/60 focus:outline-none"
								/>
								<button
									onclick={confirmPhases}
									disabled={busy}
									class="shrink-0 rounded-sm border border-amber-500/60 px-2 text-[10px] tracking-[0.16em] text-amber-300 uppercase hover:bg-amber-500/10 disabled:opacity-40"
								>
									convert
								</button>
								<button
									onclick={() => (needPhasesFor = null)}
									class="shrink-0 rounded-sm border border-stone-800 px-2 text-[10px] tracking-[0.16em] text-stone-500 uppercase hover:text-stone-300"
								>
									cancel
								</button>
							</div>
						</div>
					{/if}
				</div>

				{#if strands.length}
					<label class="block">
						<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Strand</span>
						<select
							value={node.strand}
							disabled={busy}
							onchange={(e) =>
								run(() => patchNode(domainId, node.id, { strand: e.currentTarget.value }))}
							class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
						>
							{#each strands as s (s)}
								<option value={s}>{s}</option>
							{/each}
						</select>
					</label>
				{/if}

				<div class="grid grid-cols-2 gap-3">
					<label class="block">
						<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Tier</span>
						<input
							type="number"
							min="1"
							max="40"
							bind:value={draft.tier}
							class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
						/>
					</label>
					{#if node.kind === 'project'}
						<!-- A project has no session target. Showing one would invite
						     exactly the invented number this kind exists to prevent. -->
						<div class="block">
							<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Phases</span>
							<p
								class="mt-1 truncate rounded-sm border border-stone-800 bg-black/20 px-2 py-1.5 font-mono text-[11px] text-stone-400"
								title={node.phases.join(' · ')}
							>
								{node.phases.length} · edit in the .toml
							</p>
						</div>
					{:else}
						<label class="block">
							<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">
								Estimated {kinds[node.kind].unit}
							</span>
							<input
								type="number"
								min="1"
								bind:value={draft.estimate}
								class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
							/>
						</label>
					{/if}
				</div>

				{#if node.calibration.actual}
					{@const c = node.calibration}
					<!-- The estimate is a hypothesis; the gate is the experiment. This
					     line is the result, and it is the only reason the number is
					     worth writing down. -->
					<div class="rounded-sm border border-stone-800 bg-black/20 px-2.5 py-2">
						<div class="flex items-baseline justify-between">
							<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">
								{c.settled ? 'Took' : 'So far'}
							</span>
							<span class="font-mono text-[11px] tabular-nums">
								<span class="text-stone-200">{c.actual}</span>
								<span class="text-stone-600"> / {c.estimate} est</span>
								{#if c.delta !== 0}
									<span class={c.over ? 'text-amber-400' : 'text-emerald-400'}>
										{c.delta > 0 ? '+' : ''}{c.delta}
									</span>
								{/if}
							</span>
						</div>
						<p class="mt-1 text-[10px] text-stone-600">
							{#if !c.settled}
								Still running — nothing stops you going past the estimate.
							{:else if c.delta === 0}
								Estimate was exact.
							{:else if c.over}
								Estimate was low by {c.delta}. The gate cost {Math.round(
									(c.ratio ?? 1) * 100
								)}% of the guess.
							{:else}
								Estimate was high by {-c.delta}. The gate came at {Math.round(
									(c.ratio ?? 1) * 100
								)}% of the guess.
							{/if}
						</p>
					</div>
				{/if}

				<label class="block">
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">
						Minimum per session
					</span>
					<input
						type="text"
						bind:value={draft.min_each}
						placeholder="25 min"
						class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
					/>
					<span class="mt-1 block text-[10px] text-stone-600">
						Displayed only. A click carries no duration, so this is never measured.
					</span>
				</label>

				<label class="block">
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Gate</span>
					<textarea
						bind:value={draft.gate}
						rows="2"
						placeholder="What being done actually means"
						class="mt-1 w-full resize-y rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
					></textarea>
					<span class="mt-1 block text-[10px] text-stone-600">
						You decide when this is met. The app never evaluates it.
					</span>
				</label>

				<label class="block">
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">
						Entry — how to start
					</span>
					<textarea
						bind:value={entryDraft}
						rows="4"
						placeholder={'One per line:\nBook: …\nFree: …\nSearch: …'}
						class="mt-1 w-full resize-y rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
					></textarea>
					<span class="mt-1 block text-[10px] text-stone-600">
						Books, courses, search terms. One per line, blank lines dropped. Stored
						and shown, never parsed.
					</span>
				</label>

				<label class="block">
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Note</span>
					<textarea
						bind:value={draft.note}
						rows="2"
						class="mt-1 w-full resize-y rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
					></textarea>
				</label>

				<div class="flex gap-2">
					<button
						onclick={save}
						disabled={!dirty || busy}
						class="flex-1 rounded-sm border border-amber-500/60 bg-amber-500/10 py-1.5 text-[11px] tracking-[0.16em] text-amber-300 uppercase transition hover:bg-amber-500/20 disabled:opacity-30"
					>
						{dirty ? 'save changes' : 'saved'}
					</button>
					{#if dirty}
						<button
							onclick={() => (draft = { ...node })}
							class="rounded-sm border border-stone-800 px-3 text-[11px] tracking-[0.16em] text-stone-500 uppercase hover:text-stone-300"
						>
							revert
						</button>
					{/if}
				</div>

				{#if node.kind === 'exam'}
					<label class="block">
						<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Scheduled</span>
						<input
							type="date"
							bind:value={draft.scheduled}
							class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
						/>
					</label>
				{/if}

				{#if node.kind === 'drill'}
					<label class="block">
						<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Decay days</span>
						<input
							type="number"
							min="0"
							bind:value={draft.decay_days}
							class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
						/>
						<p class="mt-1 text-[11px] text-stone-600">0 = never goes stale.</p>
					</label>
				{/if}

				{#if node.kind !== 'project'}
					<div class="grid grid-cols-2 gap-3">
						<label class="block">
							<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Metric</span>
							<input
								bind:value={draft.metric}
								placeholder="bpm"
								class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 placeholder:text-stone-700 focus:border-amber-500/60 focus:outline-none"
							/>
						</label>
						<label class="block">
							<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Target</span>
							<input
								type="number"
								min="0"
								bind:value={draft.metric_target}
								disabled={!draft.metric}
								class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 font-mono text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none disabled:opacity-40"
							/>
						</label>
					</div>
				{/if}

				<div class="border-t border-black/50 pt-3.5">
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">
						Requires ({node.requires.length})
					</span>
					<p class="mt-0.5 text-[10px] text-stone-600">Hard — these lock the node.</p>
					<div class="mt-1.5 space-y-1">
						{#each node.requires as req}
							<div
								class="flex items-center justify-between gap-2 rounded-sm border border-stone-800 bg-black/30 px-2 py-1"
							>
								<span class="truncate text-[11px] text-stone-300">{titleOf(req)}</span>
								<button
									onclick={() => run(() => disconnectNodes(domainId, req, node.id))}
									disabled={busy}
									class="shrink-0 text-[10px] text-stone-600 hover:text-rose-300"
									aria-label="Remove prerequisite {titleOf(req)}"
								>
									unlink
								</button>
							</div>
						{:else}
							<p class="text-[11px] text-stone-600">Nothing hard-blocks this node.</p>
						{/each}
					</div>
				</div>

				<div class="border-t border-black/50 pt-3.5">
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">
						Prefers ({node.prefers.length})
					</span>
					<p class="mt-0.5 text-[10px] text-stone-600">
						Soft — ordering advice. Never blocks.
					</p>
					<div class="mt-1.5 space-y-1">
						{#each node.prefers as req}
							<div
								class="flex items-center justify-between gap-2 rounded-sm border border-dashed border-stone-800 bg-black/20 px-2 py-1"
							>
								<span class="truncate text-[11px] text-stone-400">{titleOf(req)}</span>
								<button
									onclick={() => run(() => disconnectNodes(domainId, req, node.id))}
									disabled={busy}
									class="shrink-0 text-[10px] text-stone-600 hover:text-rose-300"
									aria-label="Remove soft prerequisite {titleOf(req)}"
								>
									unlink
								</button>
							</div>
						{:else}
							<p class="text-[11px] text-stone-600">None.</p>
						{/each}
					</div>
				</div>

				{#if node.metric && node.readings.length}
					<div class="border-t border-black/50 pt-3.5">
						<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">
							{node.metric} readings ({node.readings.length})
						</span>
						<div class="mt-2 flex items-end gap-px" style="height: 44px">
							{#each node.readings.slice(-40) as r (r.day)}
								{@const hi = Math.max(...node.readings.map((x) => x.value), node.metric_target || 0)}
								<div
									class="flex-1 rounded-t-[1px] bg-amber-500/60"
									style="height: {hi ? (r.value / hi) * 100 : 0}%"
									title="{r.day}: {r.value} {node.metric}"
								></div>
							{/each}
						</div>
						<p class="mt-1 font-mono text-[10px] text-stone-600">
							last {node.readings.at(-1)?.value}
							{#if node.metric_target}· target {node.metric_target}{/if}
						</p>
					</div>
				{/if}

				<div class="flex items-center gap-2 border-t border-black/50 pt-3.5">
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Order</span>
					<button
						onclick={() => run(() => reorderNode(domainId, node.id, -1))}
						disabled={busy}
						class="rounded-sm border border-stone-800 px-2 py-0.5 text-[11px] text-stone-400 hover:text-stone-200"
						aria-label="Move up within tier">↑</button
					>
					<button
						onclick={() => run(() => reorderNode(domainId, node.id, 1))}
						disabled={busy}
						class="rounded-sm border border-stone-800 px-2 py-0.5 text-[11px] text-stone-400 hover:text-stone-200"
						aria-label="Move down within tier">↓</button
					>
					<span class="text-[10px] text-stone-600">decides which sibling goes active first</span>
				</div>

				<button
					onclick={remove}
					disabled={busy}
					class="w-full rounded-sm border border-rose-900/60 py-1.5 text-[11px] tracking-[0.16em] text-rose-400/80 uppercase transition hover:bg-rose-500/10 hover:text-rose-300"
				>
					delete node
				</button>
			</div>
		{:else}
			<form
				onsubmit={(e) => {
					e.preventDefault();
					post();
				}}
			>
				<textarea
					bind:value={journalDraft}
					rows="3"
					placeholder="What happened in this session?"
					class="w-full resize-y rounded-sm border border-stone-800 bg-black/40 px-2 py-1.5 text-sm text-stone-100 focus:border-amber-500/60 focus:outline-none"
				></textarea>
				<button
					type="submit"
					disabled={busy || !journalDraft.trim()}
					class="mt-2 w-full rounded-sm border border-amber-500/60 bg-amber-500/10 py-1.5 text-[11px] tracking-[0.16em] text-amber-300 uppercase disabled:opacity-30"
				>
					add entry
				</button>
			</form>

			<div class="mt-4 space-y-2.5">
				{#each node.journal as item}
					<article class="rounded-sm border border-stone-800 bg-black/30 px-3 py-2">
						<p class="font-mono text-[10px] text-stone-600">
							{item.day} · {new Date(item.ts).toLocaleTimeString([], {
								hour: '2-digit',
								minute: '2-digit'
							})}
						</p>
						<p class="mt-1 text-[13px] leading-relaxed whitespace-pre-wrap text-stone-300">
							{item.text}
						</p>
					</article>
				{:else}
					<p class="text-[11px] text-stone-600">
						No entries yet. These are append-only — once written, an entry stays in the log.
					</p>
				{/each}
			</div>
		{/if}
	</div>
</aside>
