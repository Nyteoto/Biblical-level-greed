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
	 * how heavily this app chooses to set them is not the corpus's business.
	 *
	 * ## Lifting
	 *
	 * A lifted tag is drawn without its brackets and without its weight — as the
	 * word it has become. Nothing is edited to do it: the log holds the line as
	 * it was typed, `<garden>` still files into whatever claimed `garden`, and
	 * putting the tag back is one event away. See `lifted.svelte.ts`.
	 *
	 * Only `<tags>` can be lifted, which is a fact about the syntax rather than
	 * a decision: a tag is the one kind whose sigil wraps the word on both
	 * sides, so it is the only one whose removal leaves the sentence reading
	 * exactly as it was written. `\pattern`, `@place` and `{time}` all leave
	 * something behind.
	 *
	 * The kinds come from a second `tokenize` of the same line rather than from
	 * a field on the segment. `colorize.ts` is pinned by 25 fixtures compared
	 * key for key — an extra key on a segment fails them — and the alignment
	 * this relies on is the module's own documented rule: every token gets a
	 * segment, so the indices are the same indices.
	 *
	 * ## Quiet
	 *
	 * The tag of the folder you are reading is drawn dim, at the prose's own
	 * weight — see `quiet.ts`. The same second `tokenize` finds it. */
	import { colorizeSegments } from './colorize';
	import { tokenize } from './tokenize';
	import { lifted } from './lifted.svelte';
	import { isQuiet } from './quiet';

	let { text }: { text: string } = $props();

	const store = lifted();
	const quiet = isQuiet();
	const segments = $derived(colorizeSegments(text));
	const tokens = $derived(tokenize(text));

	/** What to draw for one segment: the raw text, or a lifted tag's bare word.
	 *  `value` is the inner content already lowercased, so the brackets are
	 *  sliced off the raw rather than taken from it — a tag written `<Garden>`
	 *  is lifted to `Garden`, which is what was typed. */
	function shown(index: number): { text: string; lift: boolean; quiet: boolean } {
		const token = tokens[index];
		const hushed = !!token && token.kind === 'folder' && quiet(token.value);
		if (!token || token.kind !== 'folder' || !store.has(token.value)) {
			return { text: segments[index].text, lift: false, quiet: hushed };
		}
		return { text: token.raw.slice(1, -1), lift: true, quiet: hushed };
	}

	function paint(color: string | null | undefined, cell: { lift: boolean; quiet: boolean }) {
		if (!color || cell.lift) return undefined;
		if (cell.quiet) return 'color:var(--color-neutral-600)';
		return `color:${color};font-weight:700`;
	}
</script>

{#each segments as s, i (i)}{@const cell = shown(i)}<span
		style={paint(s.color, cell)}
		>{cell.text}</span
	>{/each}
