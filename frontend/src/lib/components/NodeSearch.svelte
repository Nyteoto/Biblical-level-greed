<script lang="ts">
	import type { TreeNode } from '$lib/api';
	import { roman } from '$lib/api';

	let {
		nodes,
		tone = 'text-amber-300',
		accent = 'border-amber-500/40',
		onpick
	}: {
		nodes: TreeNode[];
		tone?: string;
		accent?: string;
		onpick: (id: string) => void;
	} = $props();

	let query = $state('');
	let input = $state<HTMLInputElement | null>(null);

	/** Everything on a node that carries words worth finding.
	 *
	 * Ordered by how likely it is to be what you meant: a hit in the title is
	 * the answer, a hit in the id almost never is. The first field to match is
	 * the one whose text gets quoted back.
	 *
	 * `note` here is the node's own note field from the .toml — not the
	 * domain's folder of markdown documents, which belong to no single node and
	 * so could not be named as one in the results. */
	const FIELDS: { label: string; of: (n: TreeNode) => string }[] = [
		{ label: 'title', of: (n) => n.title },
		{ label: 'gate', of: (n) => n.gate },
		{ label: 'note', of: (n) => n.note },
		{ label: 'entry', of: (n) => n.entry.join(' · ') },
		{ label: 'phases', of: (n) => n.phases.join(' · ') },
		{ label: 'strand', of: (n) => n.strand },
		{ label: 'metric', of: (n) => n.metric },
		{ label: 'id', of: (n) => n.id }
	];

	const LIMIT = 14;

	/** The text around a hit, with the hit itself split out so it can be marked
	 *  up as elements rather than injected as HTML. */
	function quote(text: string, needle: string, pad = 46) {
		const at = text.toLowerCase().indexOf(needle);
		if (at < 0) return null;
		const from = Math.max(0, at - pad);
		const to = Math.min(text.length, at + needle.length + pad);
		return {
			before: (from > 0 ? '…' : '') + text.slice(from, at),
			hit: text.slice(at, at + needle.length),
			after: text.slice(at + needle.length, to) + (to < text.length ? '…' : '')
		};
	}

	const needle = $derived(query.trim().toLowerCase());

	const results = $derived.by(() => {
		if (needle.length < 2) return [];
		const found = [];
		for (const node of nodes) {
			const where: string[] = [];
			let quoted: ReturnType<typeof quote> = null;
			let quotedFrom = '';
			for (const field of FIELDS) {
				const text = field.of(node) ?? '';
				if (!text.toLowerCase().includes(needle)) continue;
				where.push(field.label);
				if (!quoted) {
					quoted = quote(text, needle);
					quotedFrom = field.label;
				}
			}
			if (where.length) found.push({ node, where, quoted, quotedFrom });
		}
		// Title hits first, then by tier: the shallowest match is the one you can
		// act on soonest.
		return found.sort((x, y) => {
			const xt = x.where.includes('title') ? 0 : 1;
			const yt = y.where.includes('title') ? 0 : 1;
			return xt - yt || x.node.tier - y.node.tier;
		});
	});

	const shown = $derived(results.slice(0, LIMIT));

	function pick(id: string) {
		onpick(id);
		query = '';
		input?.blur();
	}

	function onkey(event: KeyboardEvent) {
		if (event.key === 'Escape') {
			query = '';
			input?.blur();
		} else if (event.key === 'Enter' && shown.length) {
			pick(shown[0].node.id);
		}
	}
</script>

<div class="relative mx-auto mt-2 w-full max-w-md">
	<div class="flex items-center gap-2 rounded-sm border {accent} bg-black/30 px-2.5 py-1.5">
		<svg
			viewBox="0 0 24 24"
			fill="none"
			stroke="currentColor"
			stroke-width="1.7"
			class="h-3.5 w-3.5 shrink-0 text-stone-500"
			aria-hidden="true"
		>
			<circle cx="11" cy="11" r="7" />
			<path d="M20 20l-3.5-3.5" stroke-linecap="round" />
		</svg>
		<input
			bind:this={input}
			bind:value={query}
			onkeydown={onkey}
			type="search"
			placeholder="Search gates, notes, entry material…"
			aria-label="Search this tree"
			class="min-w-0 flex-1 bg-transparent text-[12px] text-stone-200 placeholder:text-stone-600 focus:outline-none"
		/>
		{#if needle.length >= 2}
			<span class="shrink-0 font-mono text-[10px] text-stone-500">
				{results.length}
			</span>
		{/if}
	</div>

	{#if needle.length >= 2}
		<!-- Docked over the canvas rather than pushing it down: the tree must not
		     reflow while you are reading results off it. -->
		<div
			class="absolute inset-x-0 top-full z-30 mt-1 max-h-[min(60dvh,26rem)] overflow-y-auto rounded-sm border border-stone-800 bg-[#171310] shadow-2xl"
		>
			{#if !results.length}
				<p class="px-3 py-3 text-center text-[11px] text-stone-500">
					Nothing in this tree mentions “{query.trim()}”.
				</p>
			{:else}
				{#each shown as { node, where, quoted, quotedFrom } (node.id)}
					<button
						onclick={() => pick(node.id)}
						class="block w-full border-b border-black/50 px-3 py-2 text-left transition last:border-b-0 hover:bg-white/5"
					>
						<div class="flex items-baseline gap-2">
							<span class="shrink-0 font-mono text-[10px] text-stone-500">
								{roman(node.tier)}
							</span>
							<span class="min-w-0 flex-1 truncate text-[12px] {tone}">
								{node.title}
							</span>
							<span class="shrink-0 font-mono text-[9px] tracking-[0.1em] text-stone-600 uppercase">
								{where.join(' · ')}
							</span>
						</div>
						{#if quoted && quotedFrom !== 'title'}
							<p class="mt-0.5 text-[11px] leading-snug text-stone-400">
								{quoted.before}<mark class="bg-amber-400/25 text-amber-200">{quoted.hit}</mark
								>{quoted.after}
							</p>
						{/if}
					</button>
				{/each}
				{#if results.length > shown.length}
					<p class="px-3 py-1.5 text-center font-mono text-[10px] text-stone-600">
						+{results.length - shown.length} more — narrow the search
					</p>
				{/if}
			{/if}
		</div>
	{/if}
</div>
