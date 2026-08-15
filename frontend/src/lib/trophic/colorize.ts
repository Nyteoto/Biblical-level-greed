// Read-only rendering of a captured line — the log, the folder pages, and
// everything else that is not the capture bar.
//
// Ported from `components/ColorizedText.tsx` and pinned by `colorize.json`.
// Split out of the Svelte component so the corpus can be replayed against the
// same code the app renders: the component is now a loop over `segments`, and
// this is the whole of the behaviour.
//
// Two rules from the corpus that are easy to lose:
//
//   - **Only three kinds are coloured here.** `directive` and `todo` are not
//     in TOKEN_COLORS, so `--work` and `--todo` render as plain text once the
//     entry is saved. They are colourful only while being typed, which is the
//     point: the capture bar shows you what the syntax is doing, and the log
//     shows you what you wrote.
//   - **Every token gets a span, coloured or not**, so segment indices line
//     up with token indices. Concatenating every segment reproduces the input
//     exactly.

import { tokenize } from './tokenize';
import { TOKEN_COLORS } from './colors';

export type ColorSegment = { text: string; color: string | null };

export function colorizeSegments(text: string): ColorSegment[] {
	return tokenize(text).map((t) => ({
		text: t.raw,
		color: TOKEN_COLORS[t.kind] ?? null
	}));
}

/** The same thing as markup. Only used by the corpus check; the component
 *  renders the segments directly rather than setting innerHTML. */
export function segmentsToHtml(segments: ColorSegment[]): string {
	return segments
		.map((s) => {
			const open = s.color ? `<span style="color:${s.color}">` : '<span>';
			return `${open}${escapeHtml(s.text)}</span>`;
		})
		.join('');
}

function escapeHtml(text: string): string {
	return text
		.replace(/&/g, '&amp;')
		.replace(/</g, '&lt;')
		.replace(/>/g, '&gt;')
		.replace(/"/g, '&quot;');
}
