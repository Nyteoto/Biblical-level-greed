<script lang="ts">
	/** Read-only rendering of a captured line. Ported from ColorizedText.tsx.
	 *
	 * Written as one unbroken expression on purpose: the text renders inside a
	 * `white-space: pre-wrap` container, so any newline or indentation between
	 * the spans would show up as literal whitespace in the entry. */
	import { tokenize } from './tokenize';
	import { TOKEN_COLORS } from './colors';

	let { text }: { text: string } = $props();
	const tokens = $derived(tokenize(text));
</script>

{#each tokens as t, i (i)}{#if TOKEN_COLORS[t.kind]}<span style="color:{TOKEN_COLORS[t.kind]}"
		>{t.raw}</span
	>{:else}{t.raw}{/if}{/each}
