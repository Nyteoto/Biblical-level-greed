// Trophic's palette, re-lit for the paper-light ground.
//
// The hue assignments are the product and have never moved: blue is a folder,
// rose is a sentiment, purple is time. What moves with the shell is lightness.
// The source chose these against white (`logic/colors.ts`: #3b82f6, #9333ea,
// #e11d48, #d97706, #8b5cf6) and they are *nearly* right here — but the shell
// is #f3f2f2 rather than #fff, the type is Archivo rather than a mono, and at
// 17px inside running prose the originals sit on the contrast line rather than
// over it. Each is taken down a rung or two of the same hue and given weight
// 600, which is what makes a tag read as a tag in a paragraph without the
// colour having to shout.
//
// This file went from the dark shell's 400-rung set to this one in a single
// edit and nothing else changed, which is the property worth keeping: **if the
// ground ever moves again, swap this file and nothing else.**
//
// One consequence to know about before editing: `scripts/verify-ui.ts` holds a
// `THEME` table mapping every colour emitted here back to the source colour it
// stands in for, and the corpus comparison translates through it and then
// demands an exact match. Change a value here and that table changes with it,
// or 700-odd fixtures start failing for a reason that has nothing to do with
// behaviour.

export const SYNTAX_COLORS = {
	folder: '#1e5fbf', // <pointer>
	time: '#6b3fa0', // {time-link}
	pattern: '#b42342', // \pattern
	// The directive is the accent itself: it is the one token that acts on the
	// app rather than describing the thought, and it only ever appears in the
	// capture bar.
	directive: '#ae1800', // --directive  (--color-accent-700)
	todo: '#5b3fbe' // --todo
} as const;

export const UI_COLORS = {
	ink: '#201e1d', // the text and the caret
	// The caret's halo — the source's `rgba(24,24,27,0.2)`, which is ink at 20%
	// and stays ink at 20% here because the ground came back to light.
	inkGlow: 'rgba(32,30,29,0.2)',
	muted: '#bab6b6', // neutral-400 — the resting indicator, checkbox borders
	dim: '#605d5d', // neutral-700 — timestamps, labels
	success: '#2f9e6d', // sent
	error: '#c2352b' // refused
} as const;

/** Which token kinds get colour when an entry is rendered read-only.
 *  Directives and todos are stripped from the stored text, so they never
 *  reach this map — matching the source's TOKEN_COLORS exactly. */
export const TOKEN_COLORS: Record<string, string> = {
	folder: SYNTAX_COLORS.folder,
	time: SYNTAX_COLORS.time,
	pattern: SYNTAX_COLORS.pattern
};
