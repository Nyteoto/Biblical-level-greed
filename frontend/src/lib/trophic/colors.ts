// Trophic's palette. One ramp, no hue, white as the accent.
//
// The hue assignments were the product for as long as this app had hues. They
// did not survive the monochrome re-light, and they have not come back now that
// the green has gone too — which is the point rather than a loss:
// **every tag reads the same way — the accent, bold — and the syntax is
// told apart by its delimiters, which is what they were always for.** A folder
// is `<like this>`, time is `{like this}`, a pattern is `\like-this`, a
// directive and a todo are `--like-this`. You already have to read the bracket;
// asking the colour to repeat it was doing work the punctuation had done.
//
// This replaced five hues with one axis. It is less to look at and much less to
// maintain: there is no longer a question of what colour a new token kind gets.
//
// The file went from a dark shell's 400-rung set, to a paper-light set, to a
// green phosphor, to this — four single edits, and nothing else changed any of
// the four times. That is the property worth keeping: **if the ground ever
// moves again, swap this file and nothing else.**
//
// One consequence to know about before editing: `scripts/verify-ui.ts` holds a
// `THEME` table mapping every colour emitted here back to the source colour it
// stands in for, and the corpus comparison translates through it and then
// demands an exact match. Change a value here and that table changes with it,
// or 700-odd fixtures start failing for a reason that has nothing to do with
// behaviour. Note that the mapping is many-to-one — several source hues
// collapse onto the single accent — which is why that file translates in the
// source→port direction; see the comment there.

/** The accent. The colour of anything the screen is actively saying. */
const LIT = '#ffffff';

export const SYNTAX_COLORS = {
	// All one colour, deliberately. See the note above: the delimiters carry the
	// distinction, and in a palette with no hue to spend a second colour would be
	// a decision to defend rather than a category.
	folder: LIT, // <pointer>
	time: LIT, // {time-link}
	pattern: LIT, // \pattern
	place: LIT, // @place
	count: LIT, // #count
	directive: LIT, // --directive
	todo: LIT // --todo
} as const;

export const UI_COLORS = {
	ink: LIT, // the text and the caret
	// The caret's halo. Ink at 20%, which is the same idea it has always been —
	// the accent at low alpha, drawn around the caret rather than under it.
	inkGlow: 'rgba(255,255,255,0.2)',
	muted: '#39424a', // the resting indicator, checkbox borders
	dim: '#59616a', // timestamps, labels
	success: '#ffffff', // sent — the same accent, because it is the app speaking
	error: '#ff6a5a' // refused
} as const;

/**
 * The typing glow's sweep along the capture bar's indicator, as gradient stops.
 *
 * It lives here rather than inline in the capture bar's `<defs>` because that is
 * exactly where the re-skin missed it: five hardcoded blues inside an SVG, which
 * is the one kind of place "swap this file and nothing else" cannot reach. The
 * indicator's other three states were already reading from `UI_COLORS` and were
 * re-lit for free; this one stayed the old accent's blue for a whole release.
 *
 * The shape is the source's and is unchanged — transparent at both ends,
 * brightest a quarter in from each, a rung down in the middle. That is what
 * makes it read as light travelling along the line rather than as a bar
 * switching on.
 */
export const GLOW_STOPS = [
	{ offset: '0%', color: LIT, opacity: 0 },
	{ offset: '25%', color: LIT, opacity: 1 },
	{ offset: '50%', color: '#a9bcc6', opacity: 1 },
	{ offset: '75%', color: LIT, opacity: 1 },
	{ offset: '100%', color: LIT, opacity: 0 }
] as const;

// The one deliberate exception to the ramp, and it is worth stating why.
// `error` is a refusal: the validation layer blinks a token in it when the app
// will not accept what you typed. That is the only moment the screen contradicts
// you, and it is the one thing that must not look like normal output. It is the
// only colour in the building, and it survived the skin because the rule was
// never about the green.

/** Which token kinds get colour when an entry is rendered read-only.
 *  Directives and todos are stripped from the stored text, so they never
 *  reach this map — which is the source's TOKEN_COLORS exactly, plus `place`
 *  and `count`. Both survive into the stored line the way a folder and a
 *  pattern do, so leaving either out would render `@helsinki` or `#100` as
 *  plain prose everywhere the Log shows an entry back to you. */
export const TOKEN_COLORS: Record<string, string> = {
	folder: SYNTAX_COLORS.folder,
	time: SYNTAX_COLORS.time,
	pattern: SYNTAX_COLORS.pattern,
	place: SYNTAX_COLORS.place,
	count: SYNTAX_COLORS.count
};

/**
 * Fold an arbitrary colour onto the neutral ramp, by its luminance.
 *
 * Folders carry a colour of their own. It is assigned at creation by
 * `next_color` — real, stored, user-visible data, pinned by its own corpus file
 * — and it is not this file's to reassign. But a dozen folder hues in a palette
 * that spends none is a dozen decisions nobody made.
 *
 * So the data keeps its colour and the *screen* does not show it: anything that
 * would paint a folder colour paints this instead, which preserves the relative
 * lightness the palette encodes while spending no hue on it. Brighter folder
 * colours stay brighter. Nothing else changes, and deleting this function would
 * put the hues back rather than break anything.
 */
export function toRamp(hex: string): string {
	// The refusal red is the one colour that must survive this. It exists to
	// contradict you, and a refusal folded onto the phosphor ramp would look
	// exactly like ordinary output — which is the single worst thing it could do.
	if (hex === UI_COLORS.error) return hex;

	const match = /^#?([\da-f]{6})$/i.exec(hex.trim());
	if (!match) return UI_COLORS.dim;

	const n = parseInt(match[1], 16);
	// Rec. 709 luma, on the raw sRGB values. Perceptual accuracy is not the goal
	// — preserving the palette's own ordering is.
	const luma =
		(0.2126 * ((n >> 16) & 255) + 0.7152 * ((n >> 8) & 255) + 0.0722 * (n & 255)) / 255;

	// Across the four rungs of the ramp, dimmest to lit.
	const ramp = ['#39424a', '#617079', '#a9bcc6', LIT];
	return ramp[Math.min(ramp.length - 1, Math.max(0, Math.round(luma * (ramp.length - 1))))];
}
