// The capture bar's behaviour, with the DOM taken out.
//
// Ported from `components/SmoothTextarea.tsx` and pinned by two corpus files:
// `capture_overlay.json` (26 cases — what the bar looks like for a given
// draft) and `capture_keys.json` (18 — what each key does). It lives apart
// from the Svelte component so those can be replayed against the same code
// the app runs; the component is the textarea, the measuring and the timers,
// and everything below is the rest.
//
// What the corpus pins that is easy to get wrong
// ----------------------------------------------
//
// **The caret is fake.** The native one is off (`caret-color: transparent`,
// and the textarea's own text is transparent too); what the user sees is a
// 2px div moved by a transform under `transition: transform 80ms linear`.
// That glide is the single most recognisable thing about this app, and a port
// that uses a real caret has not ported the capture bar.
//
// **The suggestion panel is upside down.** The best match is rendered LAST —
// nearest the caret on a desktop and nearest the thumb on a phone — so
// `ArrowDown` moves the highlight *down the screen* by moving *up* the array.
// `view()` returns the panel in DOM order for exactly this reason: the
// component renders the list as given rather than reversing it and getting
// the arrow keys backwards.
//
// **The caret marker split is inclusive at both ends.** `caret >= t.start &&
// caret <= t.end` matches two tokens at a boundary, and the first one wins.
//
// **An unmapped tag is the folder blue at 60% alpha** (`#3b82f699`). That
// dimming is the only signal that a tag has nowhere to go; the unassigned
// count on the mapping screen is the other half of the same idea.
//
// **Directive and todo are coloured only while typing.** Once the entry is
// saved they render as plain text — see `colorize.ts`.

import { tokenize, activeTrigger, type Token } from './tokenize';
import { buildTrie, scoredSearch, recordUse, type UsageStats } from './trie';
import { SYNTAX_COLORS, UI_COLORS } from './colors';
import type { Vocab } from './api';

// ── Tuned constants. See design_tokens.json; none of these is a default. ──

/** The fake caret's travel between positions. */
export const CARET_GLIDE = 'transform 80ms linear';
export const CARET_BLINK = 'caret-blink 1s ease-in-out infinite';
/** How long the caret stays solid after a keystroke before blinking again. */
export const BLINK_PAUSE_MS = 530;
/** A token the validation layer is objecting to. */
export const BLINK_COLOR = UI_COLORS.error;
export const BLINK_ANIMATION = 'onboard-blink 0.6s ease-in-out infinite';
/** The completion remainder shown inline, IDE-style. */
export const GHOST_COLOR = '#a1a1aa';
/** Appended to the folder blue for a tag no folder has claimed: 60% alpha. */
export const UNASSIGNED_ALPHA = '99';

export type OverlayRole = 'token' | 'marker' | 'ghost';

export type OverlaySegment = {
	text: string;
	color: string | null;
	animation: string | null;
	role: OverlayRole;
};

export type Suggestion = { label: string; color: string; selected: boolean };

export type CaptureView = {
	/** The coloured layer behind the transparent textarea, in DOM order. */
	overlay: OverlaySegment[];
	ghost: string | null;
	/** DOM order — the best match is LAST. */
	suggestions: Suggestion[];
	suggestOpen: boolean;
};

export type BarState = {
	value: string;
	caret: number;
	/** Index into the *ranked* list, where 0 is the best match. */
	suggestIdx: number;
	stats: UsageStats;
};

// ── Colour ────────────────────────────────────────────────────────────────

export function tagColor(vocab: Vocab | undefined, tagLower: string): string {
	const id = vocab?.tag_to_folder?.[tagLower];
	const folder = vocab?.folders?.find((f) => f.id === id);
	return folder?.color ?? SYNTAX_COLORS.folder + UNASSIGNED_ALPHA;
}

function tokenColor(t: Token, vocab: Vocab | undefined): string | null {
	switch (t.kind) {
		case 'folder':
			return tagColor(vocab, t.value);
		case 'time':
			return SYNTAX_COLORS.time;
		case 'pattern':
			return SYNTAX_COLORS.pattern;
		case 'place':
			return SYNTAX_COLORS.place;
		case 'directive':
			return SYNTAX_COLORS.directive;
		case 'todo':
			return SYNTAX_COLORS.todo;
		default:
			return null;
	}
}

// ── Autocomplete ──────────────────────────────────────────────────────────

function folderNames(vocab: Vocab | undefined): string[] {
	return (vocab?.folders ?? [])
		.map((f) => f.name)
		.filter((n): n is string => typeof n === 'string' && n.length > 0);
}

/** The ranked completions for wherever the caret is, best first. */
export function rankedSuggestions(state: BarState, vocab: Vocab | undefined): string[] {
	const trigger = activeTrigger(state.value, state.caret);
	if (!trigger || !vocab) return [];
	const pick = (terms: string[]) =>
		scoredSearch(buildTrie(terms), terms, trigger.query, state.stats);
	if (trigger.char === '-') return pick(folderNames(vocab));
	if (trigger.char === '<') return pick(vocab.tags);
	if (trigger.char === '{') return pick(vocab.times);
	return pick(vocab.patterns);
}

function suggestionLabel(char: string, term: string): string {
	if (char === '<') return `<${term}>`;
	if (char === '{') return `{${term}}`;
	if (char === '-') return `--${term}`;
	return `\\${term}`;
}

function suggestionColor(char: string, term: string, vocab: Vocab | undefined): string {
	if (char === '<') return tagColor(vocab, term);
	if (char === '{') return SYNTAX_COLORS.time;
	if (char === '-') return SYNTAX_COLORS.directive;
	return SYNTAX_COLORS.pattern;
}

/** The remainder the user has not typed, matched case-insensitively, with the
 *  closing bracket for `<` and `{` and none for `\` or a directive. */
function ghostFor(state: BarState, vocab: Vocab | undefined): string | null {
	const trigger = activeTrigger(state.value, state.caret);
	const ranked = rankedSuggestions(state, vocab);
	const term = ranked[state.suggestIdx];
	if (!trigger || !term) return null;
	const q = trigger.query.toLowerCase();
	const at = term.toLowerCase().indexOf(q);
	const remainder = at >= 0 ? term.slice(at + q.length) : term;
	if (!remainder) return null;
	if (trigger.char === '<') return `${remainder}>`;
	if (trigger.char === '{') return `${remainder}}`;
	return remainder;
}

// ── The view ──────────────────────────────────────────────────────────────

export function view(
	state: BarState,
	vocab: Vocab | undefined,
	blinkIndices: number[] = []
): CaptureView {
	const tokens = tokenize(state.value);
	const blink = new Set(blinkIndices);
	const ghost = ghostFor(state, vocab);

	const overlay: OverlaySegment[] = [];
	const marker = (): OverlaySegment => ({
		text: '<caret>',
		color: null,
		animation: null,
		role: 'marker'
	});

	let placed = false;
	for (let i = 0; i < tokens.length; i++) {
		const t = tokens[i];
		const blinking = blink.has(i);
		const color = blinking ? BLINK_COLOR : tokenColor(t, vocab);
		const animation = blinking ? BLINK_ANIMATION : null;
		if (!placed && state.caret >= t.start && state.caret <= t.end) {
			const cut = state.caret - t.start;
			overlay.push({ text: t.raw.slice(0, cut), color, animation, role: 'token' });
			overlay.push(marker());
			if (ghost) overlay.push({ text: ghost, color: GHOST_COLOR, animation: null, role: 'ghost' });
			overlay.push({ text: t.raw.slice(cut), color, animation, role: 'token' });
			placed = true;
		} else {
			overlay.push({ text: t.raw, color, animation, role: 'token' });
		}
	}
	if (!placed) {
		overlay.push(marker());
		if (ghost) overlay.push({ text: ghost, color: GHOST_COLOR, animation: null, role: 'ghost' });
	}

	const trigger = activeTrigger(state.value, state.caret);
	const ranked = rankedSuggestions(state, vocab);
	// Reversed into DOM order: index 0 is the best match and belongs at the
	// bottom of the panel, nearest the caret.
	const suggestions: Suggestion[] = ranked
		.map((term, i) => ({
			label: suggestionLabel(trigger!.char, term),
			color: suggestionColor(trigger!.char, term, vocab),
			selected: i === state.suggestIdx
		}))
		.reverse();

	return { overlay, ghost, suggestions, suggestOpen: ranked.length > 0 };
}

/** The caret's inline style. `pos` is measured off the marker by the
 *  component; everything else about it is fixed. */
export function caretStyle(pos: { x: number; y: number }, blinking: boolean) {
	return {
		transform: `translate(${pos.x}px, ${pos.y}px)`,
		transition: CARET_GLIDE,
		width: '2px',
		height: '1.4em',
		background: UI_COLORS.ink,
		boxShadow: `0 0 6px ${UI_COLORS.inkGlow}`,
		animation: blinking ? CARET_BLINK : 'none'
	};
}

// ── Keys ──────────────────────────────────────────────────────────────────

export type KeyEvent = {
	key: string;
	shiftKey?: boolean;
	isComposing?: boolean;
	keyCode?: number;
};

export type KeyResult = {
	state: BarState;
	/** The event was consumed here — the component calls preventDefault. */
	prevented: boolean;
	/** The event should reach the caller's handler. That is what submits. */
	forwarded: boolean;
};

/** Everything after the trigger, through the caret, replaced by the term.
 *  Exported because the panel can also be clicked, and a click accepts a term
 *  that is not the highlighted one. */
export function acceptSuggestion(state: BarState, term: string): BarState {
	const trigger = activeTrigger(state.value, state.caret);
	if (!trigger) return state;

	let before: string;
	let insert: string;
	if (trigger.char === '-') {
		before = state.value.slice(0, trigger.start);
		// Quote anything the unquoted --directive regex could not read back.
		const needsQuote = /[^\p{L}\p{N}\p{M}_-]/u.test(term);
		insert = needsQuote ? `--"${term}" ` : `--${term} `;
	} else {
		before = state.value.slice(0, trigger.start + 1); // keep the trigger char
		if (trigger.char === '<') insert = `${term}> `;
		else if (trigger.char === '{') insert = `${term}} `;
		else insert = `${term} `;
	}
	const after = state.value.slice(state.caret);

	return {
		value: before + insert + after,
		caret: before.length + insert.length,
		suggestIdx: 0,
		stats: recordUse(state.stats, term)
	};
}

export function handleKey(
	state: BarState,
	vocab: Vocab | undefined,
	ev: KeyEvent
): KeyResult {
	// While an IME is composing (Vietnamese Telex, Japanese, Korean, Chinese…)
	// every key belongs to the IME. Hijacking Enter here commits the wrong
	// thing or cuts the composed character short.
	if (ev.isComposing || ev.keyCode === 229) {
		return { state, prevented: false, forwarded: false };
	}

	const ranked = rankedSuggestions(state, vocab);
	if (ranked.length > 0) {
		const n = ranked.length;
		// Inverted, and both wrap: the panel is drawn bottom-up, so moving the
		// highlight down the screen means moving up the array.
		if (ev.key === 'ArrowDown') {
			return {
				state: { ...state, suggestIdx: (state.suggestIdx - 1 + n) % n },
				prevented: true,
				forwarded: false
			};
		}
		if (ev.key === 'ArrowUp') {
			return {
				state: { ...state, suggestIdx: (state.suggestIdx + 1) % n },
				prevented: true,
				forwarded: false
			};
		}
		if (ev.key === 'Tab' || (ev.key === 'Enter' && !ev.shiftKey)) {
			return {
				state: acceptSuggestion(state, ranked[state.suggestIdx]),
				prevented: true,
				forwarded: false
			};
		}
		// Swallowed, but it closes nothing: the panel goes away when the
		// trigger stops matching, not because a key said so.
		if (ev.key === 'Escape') {
			return { state, prevented: true, forwarded: false };
		}
	}

	return { state, prevented: false, forwarded: true };
}
