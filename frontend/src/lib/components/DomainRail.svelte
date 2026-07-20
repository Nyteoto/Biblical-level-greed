<script lang="ts">
	import { accent, type DomainView } from '$lib/api';

	interface Props {
		domains: DomainView[];
		current: string;
		oncreate: () => void;
	}

	let { domains, current, oncreate }: Props = $props();

	/** Two letters, like the nation flags in the reference. */
	const sigil = (title: string) =>
		title
			.split(/\s+/)
			.slice(0, 2)
			.map((word) => word[0])
			.join('')
			.toUpperCase()
			.slice(0, 2);
</script>

<nav
	class="flex w-16 shrink-0 flex-col items-center gap-2 border-r border-black/60 bg-[#100d0a] py-4"
	aria-label="Domains"
>
	{#each domains as domain (domain.id)}
		{@const a = accent(domain.color)}
		{@const selected = domain.id === current}
		<a
			href="/tree/{domain.id}"
			title="{domain.title} · priority {domain.priority}"
			aria-current={selected ? 'page' : undefined}
			class="relative flex h-11 w-11 items-center justify-center rounded-sm border transition
			{selected
				? `${a.border} bg-black/50`
				: 'border-stone-800/70 bg-black/20 hover:border-stone-700'}"
		>
			<span class="text-[13px] font-semibold tracking-wide {selected ? a.text : 'text-stone-500'}">
				{sigil(domain.title)}
			</span>
			{#if domain.due_today && domain.active_node && !domain.checked_today}
				<span
					class="absolute -top-1 -right-1 h-2 w-2 rounded-full {a.bg}"
					title="due today"
				></span>
			{/if}
			{#if selected}
				<span
					class="absolute top-1/2 -right-[7px] h-0 w-0 -translate-y-1/2 border-y-[6px] border-l-[7px] border-y-transparent border-l-amber-400"
				></span>
			{/if}
		</a>
	{/each}

	<button
		onclick={oncreate}
		title="New domain"
		aria-label="New domain"
		class="mt-2 flex h-11 w-11 items-center justify-center rounded-sm border border-dashed border-stone-700 text-lg text-stone-600 transition hover:border-amber-500/60 hover:text-amber-400"
	>
		+
	</button>
</nav>
