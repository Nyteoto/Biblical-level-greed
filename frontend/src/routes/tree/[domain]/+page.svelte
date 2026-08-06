<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { setXp } from '$lib/xpstore.svelte';
	import DomainForm from '$lib/components/DomainForm.svelte';
	import DomainRail from '$lib/components/DomainRail.svelte';
	import NodeForm from '$lib/components/NodeForm.svelte';
	import NodePanel from '$lib/components/NodePanel.svelte';
	import NotesFolder from '$lib/components/NotesFolder.svelte';
	import ToolShelf from '$lib/components/ToolShelf.svelte';
	import {
		accent,
		domainFace,
		connectNodes,
		createDomain,
		createNode,
		deleteDomain,
		getDashboard,
		unlockNode,
		getDomain,
		patchDomain,
		roman,
		setSeason,
		type DomainFields,
		type DomainView,
		type NodeFields,
		type SeasonFields,
		type TreeNode
	} from '$lib/api';

	const domainId = $derived(page.params.domain!);

	let domains = $state<DomainView[]>([]);
	// From the server: the app's day rolls over at GMT+7 midnight, which is not
	// necessarily the browser's idea of today.
	let todayKey = $state('');
	let view = $state<DomainView | null>(null);
	let error = $state<string | null>(null);
	let selected = $state<string | null>(null);
	let linking = $state<string | null>(null);
	let busy = $state(false);
	// What the bank holds, for the price pills. Read-only here: affordability
	// decides whether a pill is clickable, never what the board shows.
	let bank = $state(0);

	// Creation dialogs. `addingTier` doubles as the open flag and the prefill.
	let addingTier = $state<number | null>(null);
	let editingDomain = $state(false);
	let creatingDomain = $state(false);
	let formError = $state<string | null>(null);

	const a = $derived(accent(view?.color ?? 'amber'));

	async function load() {
		try {
			const [board, one] = await Promise.all([getDashboard(), getDomain(domainId)]);
			setXp(board.xp);
			bank = board.xp.bank;
			domains = board.domains;
			todayKey = board.today;
			view = one;
			error = null;
		} catch (e) {
			error = (e as Error).message;
		}
	}

	// `?note=<id>` opens straight into that node's note. A link you can bookmark
	// or send to yourself, rather than clicking down through the tree.
	//
	// Read once, not reactively: this must not re-run the effect below. And the
	// param is deliberately left in the URL — stripping it here called
	// `replaceState` before SvelteKit's router was initialised, which threw,
	// aborted this effect, and left the page with no domains loaded at all.
	const pendingNote: string | null = new URLSearchParams(page.url.search).get('note');
	let openNote = $state(false);
	// The domain's folder of written documents — notes and journal, merged.
	let readingNotes = $state(false);

	$effect(() => {
		domainId;
		selected = pendingNote;
		openNote = !!pendingNote;
		linking = null;
		addingTier = null;
		editingDomain = false;
		formError = null;
		load();
	});

	async function run(fn: () => Promise<unknown>) {
		if (busy) return;
		busy = true;
		error = null;
		try {
			await fn();
			await load();
		} catch (e) {
			error = (e as Error).message.replace(/^\d+ [^:]+: /, '');
		} finally {
			busy = false;
		}
	}

	/** Buy a node out of `sealed`. Permanent, so it asks first. */
	async function buy(node: TreeNode) {
		const ok = confirm(
			`Unlock "${node.title}" for ${node.unlock_price} XP?\n\n` +
				`This is permanent — there are no refunds. You have ${Math.floor(bank)} banked.`
		);
		if (!ok) return;
		await run(async () => {
			const res = await unlockNode(domainId, node.id);
			setXp(res.xp);
		});
	}

	function onNodeClick(node: TreeNode) {
		if (linking && linking !== node.id) {
			const source = linking;
			linking = null;
			run(() => connectNodes(domainId, source, node.id));
			return;
		}
		linking = null;
		selected = selected === node.id ? null : node.id;
		// Only the arriving `?note=` opens the note; picking a node by hand
		// opens the panel, as it always did.
		openNote = false;
	}

	/** Titled at creation: the id is slugged from it and then never changes,
	 *  because every log entry references the node by id. */
	/** Runs a dialog's submit, keeping the error inside the dialog on failure. */
	async function submitForm(fn: () => Promise<unknown>, close?: () => void) {
		if (busy) return;
		busy = true;
		formError = null;
		try {
			await fn();
			await load();
			close?.();
		} catch (e) {
			formError = (e as Error).message.replace(/^\d+ [^:]+: /, '');
		} finally {
			busy = false;
		}
	}

	const submitNode = (fields: NodeFields & { title: string }) =>
		submitForm(
			async () => {
				const res = await createNode(domainId, fields);
				selected = res.created;
			},
			() => (addingTier = null)
		);

	const submitNewDomain = (fields: DomainFields & { title: string }) =>
		submitForm(
			async () => {
				const created = await createDomain(fields);
				await goto(`/tree/${created.id}`);
			},
			() => (creatingDomain = false)
		);

	const submitDomainEdit = (fields: DomainFields & { title: string }) =>
		submitForm(
			() => patchDomain(domainId, fields),
			() => (editingDomain = false)
		);

	// Season saves on its own endpoint and keeps the dialog open, because it is
	// the one domain edit you may want to make twice in a row (state, then width).
	const submitSeason = (fields: SeasonFields) =>
		submitForm(() => setSeason(domainId, fields));

	const dropDomain = () =>
		run(async () => {
			if (!confirm(`Delete "${view?.title}"? The .toml file is removed; your log is kept.`))
				return;
			await deleteDomain(domainId);
			await goto('/tree');
		});

	// -- connector geometry -------------------------------------------------
	let canvasEl = $state<HTMLElement | null>(null);
	let cards = $state<Record<string, HTMLElement>>({});
	let edges = $state<{ d: string; done: boolean; soft: boolean }[]>([]);
	let size = $state({ w: 0, h: 0 });

	/** Right-angle routing, as in the reference: out, across the gutter, in.
	 *
	 * Hard and soft edges are both drawn — a soft edge still orders the tree —
	 * but a soft one is dashed, because it advises rather than blocks. */
	function measure() {
		if (!canvasEl || !view) return;
		const origin = canvasEl.getBoundingClientRect();
		const done = new Set(view.nodes.filter((n) => n.status === 'done').map((n) => n.id));
		const next: { d: string; done: boolean; soft: boolean }[] = [];

		for (const node of view.nodes) {
			const to = cards[node.id];
			if (!to) continue;
			const tb = to.getBoundingClientRect();
			const all = [
				...node.requires.map((id) => ({ id, soft: false })),
				...node.prefers.map((id) => ({ id, soft: true }))
			];
			for (const { id: req, soft } of all) {
				const from = cards[req];
				if (!from) continue;
				const fb = from.getBoundingClientRect();
				const x1 = fb.right - origin.left;
				const y1 = fb.top + fb.height / 2 - origin.top;
				const x2 = tb.left - origin.left - 6; // leave room for the arrowhead
				const y2 = tb.top + tb.height / 2 - origin.top;
				const mid = x1 + (x2 - x1) / 2;
				next.push({
					d:
						Math.abs(y1 - y2) < 1
							? `M ${x1} ${y1} H ${x2}`
							: `M ${x1} ${y1} H ${mid} V ${y2} H ${x2}`,
					done: done.has(req),
					soft
				});
			}
		}
		edges = next;
		size = { w: canvasEl.scrollWidth, h: canvasEl.scrollHeight };
	}

	$effect(() => {
		view;
		cards;
		if (!canvasEl) return;
		const observer = new ResizeObserver(measure);
		observer.observe(canvasEl);
		const raf = requestAnimationFrame(measure);
		return () => {
			observer.disconnect();
			cancelAnimationFrame(raf);
		};
	});

	const byTier = $derived.by(() => {
		const groups = new Map<number, TreeNode[]>();
		for (const node of view?.nodes ?? []) {
			if (!groups.has(node.tier)) groups.set(node.tier, []);
			groups.get(node.tier)!.push(node);
		}
		if (groups.size === 0) groups.set(1, []);
		const tiers = [...groups.keys()];
		// Always offer one empty column past the end so the tree can grow.
		groups.set(Math.max(...tiers) + 1, groups.get(Math.max(...tiers) + 1) ?? []);
		return [...groups.entries()].sort((x, y) => x[0] - y[0]);
	});

	const detail = $derived(view?.nodes.find((n) => n.id === selected) ?? null);
</script>

<svelte:window
	onkeydown={(e) => {
		if (e.key === 'Escape') {
			linking = null;
			selected = null;
		}
	}}
/>

<div class="relative flex h-[var(--content-height)]">
	<DomainRail {domains} current={domainId} oncreate={() => (creatingDomain = true)} />

	<section class="flex min-w-0 flex-1 flex-col">
		<header class="relative border-b border-black/50 px-6 py-3">
			<div class="flex items-center justify-center gap-3">
				<h1
					class="text-[15px] font-semibold tracking-[0.24em] {a.text}
					{view?.foundation ? '' : 'uppercase'}
					{domainFace(view?.foundation ?? false)}"
				>
					{view?.title ?? '…'}
				</h1>
				{#if !view?.foundation}
					<!-- No edit affordance: the foundation is compiled in, and the
					     server refuses to write it. -->
					<button
						onclick={() => (editingDomain = true)}
						class="text-[11px] tracking-[0.16em] text-stone-600 uppercase hover:text-stone-300"
					>
						edit
					</button>
				{/if}
			</div>
			<p class="mt-0.5 text-center font-mono text-[10px] text-stone-600">
				priority {view?.priority} · {view?.cadence_label} · {view?.done_nodes}/{view?.total_nodes}
				complete
				{#if view && view.calibration.settled_nodes}
					{@const c = view.calibration}
					{@const pct = Math.round((c.ratio ?? 1) * 100)}
					<!-- Estimating bias, weighted by node size. Reported, never acted
					     on: nothing here rewrites an estimate for you. -->
					<span class="text-stone-700"> · </span>
					<span
						title="Across {c.settled_nodes} completed nodes: {c.actual} sessions actually taken against {c.estimate} estimated."
						class={pct > 110 ? 'text-amber-500' : pct < 90 ? 'text-emerald-600' : 'text-stone-500'}
					>
						estimates run {pct}% ({c.actual}/{c.estimate} over {c.settled_nodes} settled)
					</span>
				{/if}
			</p>

			{#if linking}
				<p
					class="absolute inset-x-0 -bottom-9 z-30 mx-auto w-fit rounded-sm border border-amber-500/50 bg-[#1d1710] px-3 py-1.5 text-[11px] text-amber-300"
				>
					Pick the node that should require
					<strong>{view?.nodes.find((n) => n.id === linking)?.title}</strong>
					· Esc to cancel
				</p>
			{/if}
		</header>


		{#if error}
			<p class="border-b border-rose-500/30 bg-rose-500/10 px-6 py-2 text-[12px] text-rose-200">
				{error}
			</p>
		{/if}

		<div class="blueprint flex-1 overflow-auto p-6">
			<div bind:this={canvasEl} class="relative w-fit">
				<svg
					class="pointer-events-none absolute top-0 left-0 z-0"
					width={size.w}
					height={size.h}
					aria-hidden="true"
				>
					<defs>
						<marker
							id="arrow-on"
							viewBox="0 0 8 8"
							refX="7"
							refY="4"
							markerWidth="7"
							markerHeight="7"
							orient="auto"
						>
							<path d="M0 0 L8 4 L0 8 z" fill="currentColor" />
						</marker>
					</defs>
					{#each edges as edge}
						<path
							d={edge.d}
							fill="none"
							stroke="currentColor"
							stroke-width={edge.soft ? 1 : 1.5}
							stroke-dasharray={edge.soft ? '3 4' : undefined}
							marker-end="url(#arrow-on)"
							class={edge.done ? 'text-amber-500/80' : edge.soft ? 'text-stone-800' : 'text-stone-700'}
						/>
					{/each}
				</svg>

				<div class="relative z-10 flex items-start gap-14">
					{#each byTier as [tier, nodes] (tier)}
						<div class="flex flex-col items-center gap-7">
							<div class="font-mono text-[13px] tracking-[0.2em] text-stone-500">
								{roman(tier)}
							</div>

							{#each nodes as node (node.id)}
								{@const done = node.status === 'done'}
								{@const active = node.status === 'active'}
								{@const locked = node.status === 'locked'}
								{@const open = node.status === 'open'}
								{@const stale = node.status === 'maintenance'}
								<div class="group relative">
									<div
										bind:this={cards[node.id]}
										title={open ? `usually after ${node.waiting_on.join(', ')} — not blocked` : ''}
										class="flex h-[42px] w-[170px] items-stretch rounded-sm border transition
										{active ? 'border-amber-400/90 shadow-[0_0_18px_-4px_rgba(251,191,36,0.6)]' : ''}
										{done ? 'border-amber-700/70 bg-gradient-to-b from-[#2b1f10] to-[#1a1309]' : ''}
										{stale ? 'border-dashed border-amber-800/70 bg-black/25' : ''}
										{locked ? 'border-stone-800/80 bg-black/25 opacity-50' : ''}
										{open
											? 'border-dashed border-stone-700 bg-gradient-to-b from-[#201a14] to-[#171310] opacity-85'
											: ''}
										{node.status === 'available'
											? 'border-stone-700 bg-gradient-to-b from-[#241d16] to-[#171310]'
											: ''}
										{active ? 'bg-gradient-to-b from-[#2c2317] to-[#191410]' : ''}
										{linking && linking !== node.id
											? 'ring-1 ring-amber-400/40 hover:ring-amber-400'
											: ''}"
									>
										<span
											class="flex w-9 shrink-0 items-center justify-center border-r border-black/50 bg-black/30 font-mono text-[10px]
											{done || active ? 'text-amber-400' : 'text-stone-500'}"
										>
											{roman(node.tier)}
										</span>
										<button
											onclick={() => onNodeClick(node)}
											class="flex flex-1 items-center justify-end truncate px-2 text-right text-[11px] leading-tight
											{selected === node.id ? 'text-white' : 'text-stone-200'} hover:text-white"
										>
											<span class="truncate">{node.title}</span>
										</button>
									</div>

									{#if node.kind === 'reminder'}
										<!-- A standing sentence has nothing to count and nothing to
										     buy. Deliberately no pill at all: any number here would
										     be a costume. -->
									{:else if !node.unlocked && node.unlock_price > 0}
										{@const buyable = node.status === 'sealed'}
										{@const affordable = bank >= node.unlock_price}
										<!-- The price of starting, in the slot the accrual pill used
										     to hold. Before you own a node, what it costs is the only
										     number worth showing. Vibrant once the tree allows it:
										     a price you cannot act on yet is information, one you can
										     is an offer, and they must not look alike. -->
										<button
											onclick={(e) => (e.stopPropagation(), buy(node))}
											disabled={busy || !buyable || !affordable}
											title={buyable
												? affordable
													? `Unlock for ${node.unlock_price} XP — permanent, no refund`
													: `${node.unlock_price} XP needed · ${Math.floor(bank)} banked · ${Math.ceil(node.unlock_price - bank)} short`
												: `${node.unlock_price} XP — finish what it requires first`}
											class="absolute -bottom-[9px] left-9 flex items-center gap-1 rounded-sm border px-1.5 font-mono text-[9px] tabular-nums transition
											{buyable
												? affordable
													? `${a.buy} bg-[#1c1712] cursor-pointer ${a.glow}`
													: `${a.border} ${a.text} bg-[#1c1712] cursor-not-allowed opacity-60`
												: 'pointer-events-none border-stone-800 bg-[#1c1712] text-stone-600'}"
										>
											{node.unlock_price}
											<span class="text-[8px] opacity-60">XP</span>
										</button>
									{:else}
										<!-- Accrual, once the node is yours. A project shows phases
										     here, not days. -->
										<div
											class="pointer-events-none absolute -bottom-[9px] left-9 rounded-sm border px-1.5 font-mono text-[9px] tabular-nums
											{done
												? 'border-amber-700/70 bg-[#3a2a12] text-amber-300'
												: 'border-stone-800 bg-[#1c1712] text-stone-400'}"
										>
											{#if view?.foundation}
												<!-- No estimate, so no denominator. This is a count of
												     days kept, not progress towards being finished. -->
												{node.sessions_done}
											{:else}
												{node.progress_done}/{node.progress_target}{node.counts_sessions
													? ''
													: 'ph'}
											{/if}
										</div>
									{/if}

									{#if node.kind !== 'drill' && node.kind !== 'reminder'}
										<span
											class="pointer-events-none absolute -top-[7px] left-9 rounded-sm border border-stone-800 bg-[#1c1712] px-1 font-mono text-[8px] tracking-wider text-stone-500 uppercase"
										>
											{node.kind}
										</span>
									{/if}

									{#if done}
										<span class="absolute -bottom-[7px] right-1 text-[11px] text-amber-400">✓</span>
									{:else if node.checked_today}
										<span class="absolute -bottom-[7px] right-1 text-[11px] text-emerald-400"
											>✓</span
										>
									{/if}

									<!-- Start an edge from this node. -->
									<button
										onclick={() => (linking = linking === node.id ? null : node.id)}
										title="Draw a link from this node"
										aria-label="Draw a link from {node.title}"
										class="absolute top-1/2 -right-2.5 z-20 flex h-5 w-5 -translate-y-1/2 items-center justify-center rounded-full border border-amber-500/60 bg-[#1d1710] text-[10px] text-amber-400 opacity-0 transition-opacity group-hover:opacity-100 focus:opacity-100
										{linking === node.id ? 'opacity-100 bg-amber-500/30' : ''}"
									>
										→
									</button>
								</div>
							{/each}

							{#if !view?.foundation}
								<!-- The foundation's shape is the argument it makes. Adding a
								     node to it would be editing a claim, not planning work. -->
								<button
									onclick={() => (addingTier = tier)}
									disabled={busy}
									class="flex h-[42px] w-[170px] items-center justify-center rounded-sm border border-dashed border-stone-800 text-[11px] tracking-[0.16em] text-stone-700 uppercase transition hover:border-amber-500/50 hover:text-amber-400/80"
								>
									+ node
								</button>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		</div>
	</section>

	{#if view}
		<!-- Top-right of the canvas, clear of the tree itself. A domain's writing
		     is a destination, not a footnote in the header. -->
		<button
			onclick={() => (readingNotes = true)}
			title="{view.title} journal"
			class="absolute top-3 right-4 z-20 flex h-11 w-11 items-center justify-center rounded-full border {a.border} bg-[#171310] {a.text} shadow-lg transition hover:scale-105 hover:bg-white/5 {a.glow}"
			aria-label="Open journal"
		>
			<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" class="h-5 w-5">
				<path d="M4 4.5A1.5 1.5 0 0 1 5.5 3H18a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H5.5A1.5 1.5 0 0 1 4 18.5v-14Z" />
				<path d="M8 3v17" stroke-linecap="round" />
				<path d="M11.5 8.5h4M11.5 12h4" stroke-linecap="round" />
			</svg>
		</button>

		<!-- Docked over the empty bottom half of the canvas. Collapsed on arrival:
		     landing on a tree is about the work, not the kit. -->
		<ToolShelf {domainId} tone={a.text} accent={a.border} glow={a.glow} />
	{/if}

	{#if readingNotes && view}
		<NotesFolder {domainId} domainTitle={view.title} onclose={() => (readingNotes = false)} />
	{/if}

	{#if detail && view}
		<NodePanel
			{domainId}
			node={detail}
			nodes={view.nodes}
			strands={view.strands}
			today={todayKey}
			{openNote}
			onchange={load}
			onclose={() => (selected = null)}
		/>
	{/if}
</div>

{#if addingTier !== null && view}
	<NodeForm
		domain={view}
		tier={addingTier}
		{busy}
		error={formError}
		onsubmit={submitNode}
		oncancel={() => {
			addingTier = null;
			formError = null;
		}}
	/>
{/if}

{#if creatingDomain}
	<DomainForm
		{busy}
		error={formError}
		onsubmit={submitNewDomain}
		oncancel={() => {
			creatingDomain = false;
			formError = null;
		}}
	/>
{/if}

{#if editingDomain && view}
	<DomainForm
		domain={view}
		{busy}
		error={formError}
		onsubmit={submitDomainEdit}
		onseason={submitSeason}
		ondelete={dropDomain}
		oncancel={() => {
			editingDomain = false;
			formError = null;
		}}
	/>
{/if}
