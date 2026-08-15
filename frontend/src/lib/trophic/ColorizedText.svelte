<script lang="ts">
	/** Read-only rendering of a captured line. Ported from ColorizedText.tsx.
	 *
	 * The behaviour is in `colorize.ts`, where the corpus can reach it; this is
	 * only the loop. Written as one unbroken expression on purpose: the text
	 * renders inside a `white-space: pre-wrap` container, so any newline or
	 * indentation between the spans would show up as literal whitespace in the
	 * entry. */
	import { colorizeSegments } from './colorize';

	let { text }: { text: string } = $props();
	const segments = $derived(colorizeSegments(text));
</script>

{#each segments as s, i (i)}<span style={s.color ? `color:${s.color}` : undefined}>{s.text}</span
	>{/each}
