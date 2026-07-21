<script lang="ts">
	import Checklist from '$lib/components/Checklist.svelte';
	import NodeCard from '$lib/components/NodeCard.svelte';
	import { setXp } from '$lib/xpstore.svelte';
	import {
		accent,
		addTodo,
		completeTodo,
		declaredLoad,
		formatMinutes,
		getDashboard,
		seasons,
		setSeason,
		shapeBlurb,
		toggleSession,
		togglePhase,
		type Dashboard,
		type DomainView,
		type TreeNode
	} from '$lib/api';

	let data = $state<Dashboard | null>(null);
	let error = $state<string | null>(null);
	let busy = $state<string | null>(null);

	async function load() {
		try {
			data = await getDashboard();
			setXp(data.xp);
			error = null;
		} catch (e) {
			error = (e as Error).message;
		}
	}

	async function run(key: string, fn: () => Promise<unknown>) {
		if (busy) return;
		busy = key;
		try {
			await fn();
			await load();
		} catch (e) {
			error = (e as Error).message;
		} finally {
			busy = null;
		}
	}

	const check = (domain: DomainView, node: TreeNode, value?: number) =>
		run(node.id, () => toggleSession(domain.id, node.id, undefined, value));

	const phase = (domain: DomainView, node: TreeNode, name: string) =>
		run(node.id, () => togglePhase(domain.id, node.id, name));

	$effect(() => {
		load();
	});

	// The board is a statement about *today*. When today ends, reload it.
	$effect(() => {
		if (!data) return;
		const ms = new Date(data.next_rollover).getTime() - Date.now();
		if (ms <= 0 || ms > 2 ** 31 - 1) return;
		const timer = setTimeout(load, ms + 1000);
		return () => clearTimeout(timer);
	});

	const due = $derived((data?.domains ?? []).filter((d) => d.due_today && d.active_nodes.length));
	const resting = $derived(
		(data?.domains ?? []).filter((d) => !d.due_today && d.active_nodes.length)
	);
	// A held or parked domain has nothing active *on purpose*, which is not the
	// same as having finished its tree. Without this split, parking a domain
	// would congratulate you for completing it.
	const held = $derived(
		(data?.domains ?? []).filter((d) => !d.active_nodes.length && d.season.state !== 'high')
	);
	const finished = $derived(
		(data?.domains ?? []).filter((d) => !d.active_nodes.length && d.season.state === 'high')
	);

	// Seasons that have run out. Reported, never applied — the switch is a click.
	const ended = $derived((data?.domains ?? []).filter((d) => d.season.over));

	const declared = $derived(declaredLoad(data?.domains ?? []));

	const hold = (domain: DomainView) =>
		run(`season-${domain.id}`, () => setSeason(domain.id, { state: 'low' }));

	// Distinct busy keys so adding an item never blocks ticking one off.
	const newTodo = (text: string) => run('todo-add', () => addTodo(text));
	const tickTodo = (id: string) => run(`todo-${id}`, () => completeTodo(id));

	const rollover = $derived(
		data
			? new Date(data.next_rollover).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
			: ''
	);
</script>

<div class="mx-auto max-w-4xl px-6 py-8">
	{#if error}
		<div
			class="mb-6 rounded-sm border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200"
		>
			{error}
			<button class="ml-2 underline underline-offset-2" onclick={load}>retry</button>
		</div>
	{/if}

	{#if data}
		<div class="mb-8 flex flex-wrap items-end justify-between gap-4">
			<div>
				<h1 class="text-[15px] font-semibold tracking-[0.24em] text-stone-200 uppercase">Today</h1>
				<p class="mt-1 font-mono text-[11px] text-stone-600">
					{new Date(data.today + 'T00:00:00').toLocaleDateString([], {
						weekday: 'long',
						day: 'numeric',
						month: 'long'
					})} · resets {rollover} GMT+7
				</p>
			</div>
			<div class="flex items-end gap-7 text-right">
				<div>
					<!-- What today costs, summed off the `min_each` you typed. Not a
					     score and not advice — arithmetic on declared data. It exists
					     because the daily cost of the board was the one input that was
					     never visible, and six domains in season came to ten hours a
					     day without ever saying so. -->
					<div class="font-mono text-3xl tabular-nums text-stone-300">
						{formatMinutes(declared.minutes)}
					</div>
					<div class="text-[10px] tracking-[0.18em] text-stone-600 uppercase">
						declared today{declared.unquantified ? ` · +${declared.unquantified} open` : ''}
					</div>
				</div>
				<div>
					<div class="font-mono text-3xl tabular-nums text-amber-300">
						{data.done_count}<span class="text-stone-700">/{data.due_count}</span>
					</div>
					<div class="text-[10px] tracking-[0.18em] text-stone-600 uppercase">domains cleared</div>
				</div>
			</div>
		</div>

		{#each ended as domain (domain.id)}
			{@const a = accent(domain.color)}
			<div
				class="mb-3 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-sm border border-emerald-500/40 bg-emerald-500/5 px-4 py-3 text-[13px]"
			>
				<span class="text-[11px] font-semibold tracking-[0.2em] uppercase {a.text}">
					{domain.title}
				</span>
				<span class="text-stone-300">
					season over — {domain.season.reason}.
				</span>
				<span class="text-stone-500">
					Nothing has changed yet; the board still shows it in season.
				</span>
				<button
					onclick={() => hold(domain)}
					disabled={busy === `season-${domain.id}`}
					class="ml-auto shrink-0 rounded-sm border border-emerald-500/50 px-3 py-1 text-[10px] tracking-[0.18em] text-emerald-300 uppercase hover:bg-emerald-500/10 disabled:opacity-30"
				>
					move to holding
				</button>
			</div>
		{/each}

		{#each data.errors as message}
			<div
				class="mb-3 rounded-sm border border-amber-600/40 bg-amber-500/10 px-4 py-2.5 font-mono text-xs text-amber-200"
			>
				{message}
			</div>
		{/each}


		<!-- Not a tree. Specific one-off things with no tier, no gate and no
		     accrual, which would be nonsense as nodes. Sits above the board
		     because the list never resets: buried items are forgotten items. -->
		<Checklist
			items={data.todos}
			today={data.today}
			busy={busy === 'todo-add'}
			onadd={newTodo}
			oncomplete={tickTodo}
		/>

		{#if !data.domains.length}
			<div class="rounded-sm border border-dashed border-stone-800 px-6 py-16 text-center">
				<p class="text-sm text-stone-400">No domains yet.</p>
				<a
					href="/tree"
					class="mt-4 inline-block rounded-sm border border-amber-500/60 px-4 py-2 text-[11px] tracking-[0.18em] text-amber-300 uppercase hover:bg-amber-500/10"
				>
					build your first tree
				</a>
			</div>
		{/if}

		<div class="space-y-6">
			{#each due as domain (domain.id)}
				{@const a = accent(domain.color)}
				<section>
					<!-- A ladder needs no header: one row says everything. Anything with
					     more than one active node gets one, so it is obvious *why* the
					     board is showing you several things at once. -->
					{#if domain.shape !== 'ladder' || domain.active_nodes.length > 1 || domain.season.state === 'low'}
						<div class="mb-2 flex flex-wrap items-baseline gap-2.5">
							<a
								href="/tree/{domain.id}"
								class="text-[11px] font-semibold tracking-[0.2em] uppercase {a.text} hover:underline"
							>
								{domain.title}
							</a>
							{#if domain.season.state === 'low'}
								<!-- Say plainly that these cards are upkeep, not progress.
								     A held domain shows only what is about to go stale, and
								     mistaking that for advancement is the whole risk. -->
								<span
									class="rounded-sm border px-1.5 py-px font-mono text-[9px] tracking-[0.14em] uppercase {seasons
										.low.tone}"
								>
									holding · about to go stale
								</span>
							{:else if domain.season.strands.length}
								<span class="font-mono text-[10px] text-stone-600">
									in season: {domain.season.strands.join(', ')}
								</span>
							{/if}
							<span class="font-mono text-[10px] text-stone-600">
								{shapeBlurb[domain.shape]} · {domain.cadence_label}
							</span>
							{#if domain.season.days_left !== null && domain.season.state === 'high'}
								<span class="font-mono text-[10px] text-stone-700">
									{domain.season.days_left}d left
								</span>
							{/if}
						</div>
					{/if}

					<div class="space-y-2.5">
						{#each domain.active_nodes as node (node.id)}
							<NodeCard
								{node}
								color={domain.color}
								domainId={domain.id}
								strandLabel={domain.shape === 'strands'
									? node.strand
									: domain.shape === 'ladder'
										? domain.title
										: ''}
								busy={busy === node.id}
								onCheck={(value) => check(domain, node, value)}
								onPhase={(name) => phase(domain, node, name)}
							/>
						{/each}
					</div>
				</section>
			{/each}
		</div>

		{#if resting.length}
			<h3 class="mt-9 mb-2.5 text-[10px] font-semibold tracking-[0.2em] text-stone-700 uppercase">
				Not due today
			</h3>
			<div class="space-y-1.5">
				{#each resting as domain (domain.id)}
					<a
						href="/tree/{domain.id}"
						class="flex items-center gap-3 rounded-sm border border-stone-800/60 bg-black/20 px-4 py-2.5 text-[13px] hover:border-stone-700"
					>
						<span
							class="shrink-0 text-[10px] font-semibold tracking-[0.2em] uppercase {accent(
								domain.color
							).text}"
						>
							{domain.title}
						</span>
						<span class="truncate text-stone-500">
							{domain.active_nodes.map((n) => n.title).join(' · ')}
						</span>
						<span class="ml-auto shrink-0 font-mono text-[10px] text-stone-700">
							{domain.cadence_label}
						</span>
					</a>
				{/each}
			</div>
		{/if}

		{#if held.length}
			<h3 class="mt-9 mb-2.5 text-[10px] font-semibold tracking-[0.2em] text-stone-700 uppercase">
				Out of season — nothing owed today
			</h3>
			<div class="space-y-1.5">
				{#each held as domain (domain.id)}
					<a
						href="/tree/{domain.id}"
						class="flex items-center gap-3 rounded-sm border border-stone-800/60 bg-black/20 px-4 py-2.5 text-[13px] hover:border-stone-700"
					>
						<span
							class="shrink-0 text-[10px] font-semibold tracking-[0.2em] uppercase {accent(
								domain.color
							).text} opacity-60"
						>
							{domain.title}
						</span>
						<span
							class="shrink-0 rounded-sm border px-1.5 py-px font-mono text-[9px] tracking-[0.14em] uppercase {seasons[
								domain.season.state
							].tone}"
						>
							{seasons[domain.season.state].label}
						</span>
						<span class="truncate text-stone-600">
							{domain.season.state === 'off'
								? 'nothing here decays — parked at no cost'
								: `${domain.season.decaying_count} nodes decay; none due yet`}
						</span>
						<span class="ml-auto shrink-0 font-mono text-[10px] text-stone-700">
							{domain.done_nodes}/{domain.total_nodes}
						</span>
					</a>
				{/each}
			</div>
		{/if}

		{#if finished.length}
			<h3 class="mt-9 mb-2.5 text-[10px] font-semibold tracking-[0.2em] text-stone-700 uppercase">
				Tree complete
			</h3>
			<div class="space-y-1.5">
				{#each finished as domain (domain.id)}
					<a
						href="/tree/{domain.id}"
						class="flex items-center gap-3 rounded-sm border border-stone-800/60 bg-black/20 px-4 py-2.5 text-[13px] hover:border-stone-700"
					>
						<span
							class="text-[10px] font-semibold tracking-[0.2em] uppercase {accent(domain.color)
								.text}"
						>
							{domain.title}
						</span>
						<span class="text-stone-600">
							{domain.done_nodes}/{domain.total_nodes} nodes — nothing left unlocked
						</span>
					</a>
				{/each}
			</div>
		{/if}
	{/if}
</div>
