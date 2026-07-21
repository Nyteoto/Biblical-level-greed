<script lang="ts">
	import { parseEntry } from '$lib/entry';

	interface Props {
		line: string;
		/** The domain's accent, so a link reads as belonging to this tree. */
		tone?: string;
	}

	let { line, tone = 'text-amber-300' }: Props = $props();

	const segments = $derived(parseEntry(line));
</script>

{#each segments as segment, i (i)}{#if segment.href}<a
			href={segment.href}
			target="_blank"
			rel="noopener noreferrer"
			onclick={(e) => e.stopPropagation()}
			class="{tone} underline decoration-dotted underline-offset-2 transition hover:decoration-solid"
			>{segment.text}</a
		>{:else}{segment.text}{/if}{/each}
