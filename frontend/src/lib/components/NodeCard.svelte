<script lang="ts">
	import EntryLine from './EntryLine.svelte';
	import { entryLinks } from '$lib/entry';
	import { accent, kinds, roman, type TreeNode } from '$lib/api';

	interface Props {
		node: TreeNode;
		color: string;
		domainId: string;
		/** Shown above the title on strand domains. */
		strandLabel?: string;
		busy?: boolean;
		onCheck?: (value?: number) => void;
		onPhase?: (phase: string) => void;
	}

	let {
		node,
		color,
		domainId,
		strandLabel = '',
		busy = false,
		onCheck,
		onPhase
	}: Props = $props();

	const a = $derived(accent(color));
	const meta = $derived(kinds[node.kind]);

	// The openable half of `entry`, deduped. Stays on the card for the life of
	// the node: knowing where to start is a day-one question, but *opening the
	// thing* is a question every single day, and making that a tap rather than a
	// navigation is the whole point.
	const links = $derived(entryLinks(node.entry));

	// A project has no session counter at all — its progress is phases ticked.
	const isProject = $derived(node.kind === 'project');
	const pct = $derived(
		node.progress_target ? Math.min(100, (node.progress_done / node.progress_target) * 100) : 0
	);
	// Past the estimate is not an error and must not be hidden. The bar fills,
	// then a second bar shows the overshoot as its own quantity — clamping it
	// silently would throw away half of what the estimate is being tested on.
	const overshoot = $derived(Math.max(0, node.progress_done - node.progress_target));
	const overPct = $derived(
		node.progress_target ? Math.min(100, (overshoot / node.progress_target) * 100) : 0
	);

	// `open` means only soft prerequisites are unmet. It must look startable,
	// because in filmmaking and ensemble playing, starting early is the method.
	const isOpen = $derived(node.status === 'open');
	const isStale = $derived(node.status === 'maintenance');

	let reading = $state('');

	function check() {
		const n = reading.trim() === '' ? undefined : Number(reading);
		onCheck?.(Number.isFinite(n as number) ? (n as number) : undefined);
		reading = '';
	}

	const latest = $derived(node.readings.at(-1)?.value ?? null);
	const best = $derived(
		node.readings.length ? Math.max(...node.readings.map((r) => r.value)) : null
	);

	// A sparkline over the last 20 readings. Plain SVG, no library.
	const spark = $derived.by(() => {
		const rs = node.readings.slice(-20);
		if (rs.length < 2) return '';
		const vals = rs.map((r) => r.value);
		const lo = Math.min(...vals);
		const hi = Math.max(...vals);
		const span = hi - lo || 1;
		return rs
			.map((r, i) => {
				const x = (i / (rs.length - 1)) * 100;
				const y = 20 - ((r.value - lo) / span) * 18;
				return `${x.toFixed(1)},${y.toFixed(1)}`;
			})
			.join(' ');
	});
</script>

<article
	class="flex items-stretch gap-4 rounded-sm border bg-gradient-to-b from-[#1e1811] to-[#171310] p-4 transition
	{node.checked_today
		? 'border-stone-800/70 opacity-55'
		: isOpen
			? 'border-dashed border-stone-700'
			: `${a.border} ${a.glow}`}"
>
	<span
		class="flex w-10 shrink-0 items-center justify-center rounded-sm border border-black/50 bg-black/30 font-mono text-[11px] {a.text}"
	>
		{roman(node.tier)}
	</span>

	<div class="min-w-0 flex-1">
		<div class="flex flex-wrap items-center gap-2">
			{#if strandLabel}
				<span class="text-[10px] font-semibold tracking-[0.2em] uppercase {a.text}">
					{strandLabel}
				</span>
			{/if}
			<span
				class="rounded-sm border border-stone-800 px-1.5 py-px font-mono text-[9px] tracking-wider text-stone-500 uppercase"
				title={meta.hint}
			>
				{meta.label}
			</span>
			{#if node.kind === 'social'}
				<span class="text-[10px] text-stone-500">· needs other people</span>
			{/if}
			{#if isStale}
				<span class="text-[10px] text-amber-500">· gone stale, needs upkeep</span>
			{/if}
		</div>

		<h2
			class="mt-1 truncate text-[15px] font-medium {node.checked_today
				? 'text-stone-600 line-through decoration-stone-700'
				: 'text-stone-100'}"
		>
			{node.title}
		</h2>

		{#if isOpen && node.waiting_on.length}
			<!-- Advice, not a block. Deliberately phrased as a shrug. -->
			<p class="mt-0.5 text-[11px] text-stone-500 italic">
				usually after {node.waiting_on.join(', ')} — but you can start now
			</p>
		{:else if node.min_each}
			<p class="mt-0.5 text-[12px] text-stone-500">
				at least <span class="text-stone-300">{node.min_each}</span>
				<span class="text-stone-700"> · honour system</span>
			</p>
		{/if}

		{#if node.entry.length && node.progress_done === 0}
			<!-- The full text, but only before the first session: `entry` answers
			     "where do I even start", which stops being a question once you have
			     started. The links below outlive it. -->
			<ul class="mt-2 space-y-0.5 border-l border-stone-800 pl-2.5">
				{#each node.entry as line (line)}
					<li class="text-[11px] leading-snug text-stone-500">
						<EntryLine {line} tone={a.text} />
					</li>
				{/each}
			</ul>
		{:else if links.length}
			<!-- Past the first session the prose is noise and the materials are not.
			     Just the things to open, in one row you can thumb. -->
			<div class="mt-2 flex flex-wrap items-center gap-1.5">
				<span class="text-[9px] tracking-[0.16em] text-stone-700 uppercase">open</span>
				{#each links.slice(0, 4) as link (link.href)}
					<a
						href={link.href}
						target="_blank"
						rel="noopener noreferrer"
						title={link.text}
						class="max-w-[15rem] truncate rounded-sm border border-stone-800 px-1.5 py-0.5 text-[10px] {a.text} transition hover:border-stone-700 hover:bg-white/5"
					>
						{link.text}
					</a>
				{/each}
			</div>
		{/if}

		{#if isProject}
			<!-- No session bar. A shoot day is not 12% completable. -->
			<div class="mt-2.5 flex flex-wrap gap-1.5">
				{#each node.phases as phase (phase)}
					{@const done = node.phases_done.includes(phase)}
					<button
						onclick={() => onPhase?.(phase)}
						disabled={busy || !onPhase}
						class="rounded-sm border px-2 py-1 text-[11px] transition disabled:opacity-50
						{done
							? `${a.border} ${a.text} bg-black/30`
							: 'border-stone-800 text-stone-500 hover:border-stone-600 hover:text-stone-300'}"
					>
						{done ? '☑' : '☐'}
						{phase}
					</button>
				{/each}
			</div>
			<p class="mt-2 font-mono text-[10px] text-stone-600">
				{node.progress_done}/{node.progress_target} phases
			</p>
		{:else}
			<div class="mt-2.5 flex flex-wrap items-center gap-3">
				{#if node.kind === 'exam'}
					{#if node.scheduled}
						<span class="font-mono text-[11px] {a.text}">
							{node.scheduled}
							{#if node.days_until !== null}
								<span class="text-stone-500">
									· {node.days_until > 0
										? `${node.days_until} days`
										: node.days_until === 0
											? 'today'
											: 'past'}
								</span>
							{/if}
						</span>
					{:else}
						<span class="font-mono text-[11px] text-stone-600">no date — register first</span>
					{/if}
				{/if}

				<div class="relative h-1 w-32 overflow-hidden rounded-full bg-black/50">
					<div
						class="h-full rounded-full {a.bg} transition-all duration-300"
						style="width: {pct}%"
					></div>
					{#if overshoot}
						<!-- Overshoot rides on top, striped, so it reads as a different
						     quantity rather than as more progress. -->
						<div
							class="absolute inset-y-0 left-0 rounded-full bg-stone-500/60 transition-all duration-300"
							style="width: {overPct}%"
						></div>
					{/if}
				</div>
				<span class="font-mono text-[10px] tabular-nums text-stone-600">
					{#if node.progress_target}
						{node.progress_done}/{node.progress_target}
					{:else}
						<!-- No estimate — the foundation's drills are perpetual, so a
						     denominator would be inventing a finish line. -->
						{node.progress_done}
					{/if}
					{meta.unit}
					{#if overshoot}
						<span class="text-stone-500">+{overshoot} over est.</span>
					{/if}
				</span>

				{#if node.metric && latest !== null}
					<span class="font-mono text-[10px] text-stone-500">
						last <span class="text-stone-300">{latest}</span>
						{node.metric}
						{#if best !== null && node.metric_target}
							<span class="text-stone-700">· best {best} / {node.metric_target}</span>
						{/if}
					</span>
				{/if}

				{#if spark}
					<svg viewBox="0 0 100 20" class="h-4 w-20" preserveAspectRatio="none" aria-hidden="true">
						<polyline
							points={spark}
							fill="none"
							stroke="currentColor"
							stroke-width="1.5"
							vector-effect="non-scaling-stroke"
							class={a.text}
						/>
					</svg>
				{/if}

				{#if node.ready_to_complete}
					<a
						href="/tree/{domainId}"
						class="rounded-sm border border-emerald-500/50 px-2 py-0.5 text-[10px] text-emerald-300 hover:bg-emerald-500/10"
					>
						target met — review the gate
					</a>
				{/if}
			</div>
		{/if}
	</div>

	{#if !isProject && onCheck}
		<div class="flex w-24 shrink-0 flex-col items-stretch gap-1">
			{#if node.metric && !node.checked_today}
				<!-- The reading is optional. The app stores the number you type and
				     does nothing clever with it. -->
				<input
					bind:value={reading}
					type="number"
					inputmode="numeric"
					placeholder={node.metric}
					aria-label="{node.metric} reached today"
					class="w-full rounded-sm border border-stone-800 bg-black/40 px-1.5 py-1 text-center font-mono text-[11px] text-stone-200 placeholder:text-stone-700 focus:border-stone-600 focus:outline-none"
				/>
			{/if}
			<button
				onclick={check}
				disabled={busy}
				aria-pressed={node.checked_today}
				aria-label="{node.checked_today ? 'Undo' : 'Check off'} {node.title}"
				class="flex flex-1 flex-col items-center justify-center gap-1 rounded-sm border py-2 text-[10px] tracking-[0.16em] uppercase transition disabled:opacity-40
				{node.checked_today
					? 'border-stone-800 text-stone-600 hover:text-stone-400'
					: `${a.border} ${a.text} hover:bg-black/30`}"
			>
				{#if node.checked_today}
					<svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
						<path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round" />
					</svg>
					done
				{:else}
					<span class="text-xl leading-none">＋</span>
					{node.kind === 'social' ? 'log one' : 'check off'}
				{/if}
			</button>
		</div>
	{/if}
</article>
