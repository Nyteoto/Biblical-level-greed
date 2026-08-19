<script lang="ts">
	/**
	 * The four things this app counts, as marks instead of words.
	 *
	 * `0 albums · 3 entries · 3 media` is three numbers wearing three nouns, and
	 * the nouns are the longest part of it while carrying the least — you learn
	 * what the app counts once and then read the figures forever. A glyph says
	 * the same thing in a quarter of the width, which is what lets a shelf header
	 * and a card's footer hold the same information without either becoming a
	 * sentence.
	 *
	 * They are drawn to the same rules so they read as one set: a 16 box, a 1.4
	 * stroke, `currentColor` throughout. That last one is what keeps them inside
	 * the single-hue rule — a glyph is never its own colour, it is whatever the
	 * text around it is, so it dims with the label it belongs to and cannot
	 * introduce a second accent to the screen.
	 *
	 * **The word does not disappear, it moves into the label.** A number with a
	 * picture next to it is unreadable to a screen reader and ambiguous to anyone
	 * who has not met the icon yet, so each carries a `title` and an `aria-label`
	 * with the noun it replaced, and the tooltip is the same string. Dropping the
	 * word from the DOM as well as the screen would be trading clarity for
	 * density rather than buying it.
	 */
	type Kind = 'entries' | 'album' | 'media' | 'todo';

	let {
		kind,
		count,
		size = 13
	}: {
		kind: Kind;
		/** Used for the label only — `1 entry` rather than `1 entries`. The
		 *  number itself is printed by the caller, beside this. */
		count?: number;
		size?: number;
	} = $props();

	const NOUN: Record<Kind, [string, string]> = {
		entries: ['entry', 'entries'],
		album: ['album', 'albums'],
		media: ['photograph or clip', 'media'],
		// Read beside a `done/made` pair rather than beside one number, so the
		// singular is the one case where it would be read at all.
		todo: ['todo', 'todos']
	};

	const label = $derived(NOUN[kind][count === 1 ? 0 : 1]);
</script>

<svg
	width={size}
	height={size}
	viewBox="0 0 16 16"
	fill="none"
	stroke="currentColor"
	stroke-width="1.4"
	stroke-linecap="round"
	stroke-linejoin="round"
	role="img"
	aria-label={label}
	class="inline-block shrink-0 translate-y-[0.09em]"
>
	<title>{label}</title>
	{#if kind === 'entries'}
		<!-- A written line: three rules, the last one short, which is what a
		     paragraph looks like from far enough away. An entry in this app *is* a
		     line, so the mark is the thing rather than a metaphor for it. -->
		<path d="M2.5 4h11" />
		<path d="M2.5 8h11" />
		<path d="M2.5 12h6" />
	{:else if kind === 'album'}
		<!-- A folder, tab and all. An album is a folder read through one year, and
		     the folder is the half of that a mark can carry. -->
		<path d="M2 4.2a1 1 0 0 1 1-1h3.1l1.4 1.6H13a1 1 0 0 1 1 1v6.4a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1z" />
	{:else if kind === 'todo'}
		<!-- A tick inside a ring. It was a bare tick, which was wrong for the
		     set: the other three are *things* — a written line, a folder, a
		     photograph — and a tick on its own is an annotation about a thing.
		     Closed into a ring it becomes an object like the rest of them, and
		     the row of marks reads as one family.
		     The ring is drawn a hair inside the box so its stroke is not clipped
		     at 11px, and the tick is short and steep so it stays a tick rather
		     than a smear when the whole mark is a dozen pixels wide. -->
		<circle cx="8" cy="8" r="6.1" />
		<path d="M5.2 8.3 7.1 10.3 10.9 5.9" />
	{:else}
		<!-- A photograph: a frame, a sun, and the hill the light falls on. The
		     frame is drawn a little wide because at 13px a square reads as a
		     button and a landscape reads as a picture. -->
		<rect x="2" y="3.4" width="12" height="9.2" rx="1.4" />
		<circle cx="5.6" cy="6.6" r="1.05" />
		<path d="M2.4 11.4 6 8.4l2.6 2.1 2.2-1.9 2.8 2.4" />
	{/if}
</svg>
