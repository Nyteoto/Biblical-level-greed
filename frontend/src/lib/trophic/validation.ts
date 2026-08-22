// Live validation of the capture draft.
//
// Ported from `trophic/reference/ui-behavior/hooks/useCaptureValidation.ts`
// and pinned by `capture_validation.json`, 32 cases. Until the folder
// registry existed this had nothing to check against, which is why
// `SmoothTextarea` has taken a `blinkIndices` prop all along and nothing ever
// filled it.
//
// It answers one question — is this line going somewhere the user did not
// mean — and it can only answer it because a `--directive` names a folder and
// a `<tag>` names a mapping, so the two can disagree. Everything else about a
// draft is unvalidatable by construction: a tag nothing has claimed yet is not
// a mistake, it is how tags start.
//
// Three details the corpus caught, all of which look like tidying:
//
//   - **`--draw` returns early.** `--draw -Missing <garden>` reports the
//     missing draw folder and never runs the conflict check. The branch is
//     here even though `--draw` opens a sketch pad this port does not have
//     yet, because deleting it would silently change what the other branches
//     see, and putting it back later means re-deriving these rules.
//   - **The two folder-name comparisons disagree on case, on purpose.** A
//     `--directive` is matched case-insensitively; the `--draw -Name` folder
//     is matched verbatim, so `-Work` finds the folder and `-work` does not.
//     Unifying them is the obvious cleanup and it is wrong.
//   - **`locked` is every issue type, not a subset.** The field exists so an
//     advisory fourth type can be added later without changing callers.
//
// The fourth type arrived, and it is not advisory: `too-long`. It is here
// rather than left to the server because the server's refusal arrives after
// the draft has already begun sliding out of the box, and a capture that is
// refused *after* it has left the box is a capture the user has to remember.
// Length is the one thing about a draft that can be checked without asking
// anything, so it is checked while it is still being typed — which is also why
// it is the one issue that does not need `vocab` and is computed before the
// early return for it.

import { tokenize } from './tokenize';
import { COMMANDS } from './capture-bar';
import type { Vocab } from './api';

/**
 * **A command is not a missing folder.** `tokenize.ts` reserves the source's
 * nav words — `codex`, `folders`, `settings`, `assign`, `logout`, `dev`,
 * `draw` — but not `reply`, so `--reply` arrives here as an ordinary directive
 * and got the full treatment: "folder reply doesn't exist", blinking red, bar
 * locked. It is a command, and the one command that has to be typed at the
 * front of a thought you are in the middle of writing.
 *
 * The tokenizer is not the place to fix that: it is copied verbatim from the
 * file the corpus was generated from and 395 fixtures pin it, `--reply` as a
 * directive token among them. So the token stays what it is and the *meaning*
 * is decided here, where this port is allowed to have an opinion.
 *
 * `todo` is in the list for completeness rather than necessity — the tokenizer
 * already gives `--todo` its own kind, so it never reaches the directive
 * branch. Listing it anyway is what stops the next reader wondering whether
 * that is on purpose.
 */

export type ValidationIssue = {
	type: 'missing-folder' | 'conflict' | 'missing-draw-folder' | 'too-long';
	message: string;
	/** Indices into `tokenize(draft)` — not character offsets. */
	blinkIndices: number[];
	/** The folder this issue could be fixed by creating, if any. */
	createFolder?: string;
};

export type Validation = {
	issues: ValidationIssue[];
	/** True when the draft must not be sent as it stands. */
	locked: boolean;
};

const DRAW_RE = /^--draw\s+-(.+)$/i;

/** The longest a capture may be, mirroring `backend/capture/config.py`. The
 *  two have to agree: this one is what stops the send, that one is what makes
 *  it true. */
export const MAX_RAW_LEN = 20000;

/** Where the counter starts showing itself: the last tenth of the room. Early
 *  enough to change what you are writing, late enough that an ordinary line
 *  never sees it. */
export const CAP_WARN_AT = MAX_RAW_LEN - MAX_RAW_LEN / 10;

export function validate(
	draft: string,
	vocab: Vocab | undefined,
	/** Characters the send will add that the draft does not show — the pinned
	 *  folder's tag, which is appended to the raw line on the way out. Counted
	 *  here so the bar never reports room the server will not honour. */
	reserved = 0
): Validation {
	// Length first, and outside the vocab guard: it is checkable with nothing
	// loaded, and it is the only issue that stays true if the fetch never
	// lands. No `blinkIndices` — there is no offending token, the whole draft
	// is the problem, and the counter under the line already says so.
	const length = draft.trim().length + (draft.trim() ? reserved : 0);
	const issues: ValidationIssue[] = [];
	if (length > MAX_RAW_LEN) {
		issues.push({
			type: 'too-long',
			message: `${length.toLocaleString()} characters — ${(
				length - MAX_RAW_LEN
			).toLocaleString()} over what a capture holds`,
			blinkIndices: []
		});
	}

	// No vocab means the fetch has not landed. Never block on that.
	if (!draft.trim() || !vocab) return { issues, locked: issues.length > 0 };

	const tokens = tokenize(draft);

	const directiveToken = tokens.find((t) => t.kind === 'directive');
	const directiveName = directiveToken?.value ?? null;

	// --draw takes its folder by name after a single dash, and everything
	// after that dash is the name, spaces included.
	const drawMatch = draft.trim().match(DRAW_RE);
	if (drawMatch) {
		const folderName = drawMatch[1].trim();
		const folder = vocab.folders.find((f) => f.name === folderName);
		if (!folder) {
			const idx = tokens.findIndex((t) => t.kind === 'text' && t.raw.includes(folderName));
			issues.push({
				type: 'missing-draw-folder',
				message: `folder "${folderName}" not found`,
				blinkIndices: idx >= 0 ? [idx] : [],
				createFolder: folderName
			});
		}
		return { issues, locked: issues.length > 0 };
	}

	if (directiveName && !COMMANDS.includes(directiveName)) {
		const folder = vocab.folders.find((f) => f.name.toLowerCase() === directiveName);
		if (!folder) {
			const idx = tokens.findIndex((t) => t.kind === 'directive');
			issues.push({
				type: 'missing-folder',
				message: `folder "${directiveName}" doesn't exist`,
				blinkIndices: idx >= 0 ? [idx] : [],
				createFolder: directiveName
			});
		}
	}

	// `--work <garden>` when <garden> belongs to Home: the line claims two
	// destinations. Both halves of the disagreement blink, so it is visible
	// which tag caused it rather than only that something did.
	if (directiveName && !COMMANDS.includes(directiveName)) {
		const directiveFolder = vocab.folders.find((f) => f.name.toLowerCase() === directiveName);
		if (directiveFolder) {
			tokens.forEach((token, index) => {
				if (token.kind !== 'folder') return;
				const assigned = vocab.tag_to_folder[token.value];
				if (!assigned || assigned === directiveFolder.id) return;
				const dirIdx = tokens.findIndex((t) => t.kind === 'directive');
				issues.push({
					type: 'conflict',
					message: `--${directiveName} and <${token.value}> conflict — they point to different folders`,
					blinkIndices: [dirIdx, index].filter((i) => i >= 0)
				});
			});
		}
	}

	const locked = issues.some(
		(i) =>
			i.type === 'conflict' ||
			i.type === 'missing-draw-folder' ||
			i.type === 'missing-folder' ||
			i.type === 'too-long'
	);

	return { issues, locked };
}
