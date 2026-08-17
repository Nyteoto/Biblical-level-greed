<script lang="ts">
	/** Read-only rendering of a captured line. Ported from ColorizedText.tsx.
	 *
	 * The behaviour is in `colorize.ts`, where the corpus can reach it; this is
	 * only the loop. Written as one unbroken expression on purpose: the text
	 * renders inside a `white-space: pre-wrap` container, so any newline or
	 * indentation between the spans would show up as literal whitespace in the
	 * entry.
	 *
	 * **Weight, not hue, is what marks a tag now.** Every kind is the same lit
	 * phosphor (see `colors.ts`), so the thing that makes a tag findable in a
	 * line of prose is that the prose around it is thin and the tag is bold. The
	 * weight is applied here rather than in `colorize.ts` on purpose: that module
	 * is replayed against the corpus, which pins the colour of each segment, and
	 * how heavily this app chooses to set them is not the corpus's business. */
	import { colorizeSegments } from './colorize';

	let { text }: { text: string } = $props();
	const segments = $derived(colorizeSegments(text));
</script>

{#each segments as s, i (i)}<span
		style={s.color ? `color:${s.color};font-weight:700` : undefined}>{s.text}</span
	>{/each}
