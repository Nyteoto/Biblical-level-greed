// Trophic's palette, re-lit for this app's dark shell.
//
// The hue assignments are the product and do not move: blue is a folder, rose
// is a sentiment, purple is time. What moved is lightness — the originals were
// chosen against white (`logic/colors.ts`: #3b82f6, #9333ea, #e11d48, #d97706,
// #8b5cf6) and every one of them is too dark to read on #14100c. Each is
// lifted to the 400 rung of the same Tailwind ramp, which keeps the
// relationships between them and gets them over the contrast line.
//
// If a light theme ever comes back, swap this file and nothing else.

export const SYNTAX_COLORS = {
	folder: '#60a5fa', // blue-400   <pointer>
	time: '#c084fc', // purple-400 {time-link}
	pattern: '#fb7185', // rose-400   \pattern
	directive: '#f59e0b', // amber-500  --directive
	todo: '#a78bfa' // violet-400 --todo
} as const;

export const UI_COLORS = {
	ink: '#e7e5e4', // stone-200 — text and the caret
	muted: '#57534e', // stone-600 — the resting indicator, checkbox borders
	dim: '#a8a29e', // stone-400 — timestamps, labels
	success: '#34d399', // emerald-400 — sent
	error: '#ef4444' // red-500 — refused
} as const;

/** Which token kinds get colour when an entry is rendered read-only.
 *  Directives and todos are stripped from the stored text, so they never
 *  reach this map — matching the source's TOKEN_COLORS exactly. */
export const TOKEN_COLORS: Record<string, string> = {
	folder: SYNTAX_COLORS.folder,
	time: SYNTAX_COLORS.time,
	pattern: SYNTAX_COLORS.pattern
};
