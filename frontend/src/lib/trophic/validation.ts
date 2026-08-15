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

import { tokenize } from './tokenize';
import type { Vocab } from './api';

export type ValidationIssue = {
	type: 'missing-folder' | 'conflict' | 'missing-draw-folder';
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

export function validate(draft: string, vocab: Vocab | undefined): Validation {
	// No vocab means the fetch has not landed. Never block on that.
	if (!draft.trim() || !vocab) return { issues: [], locked: false };

	const tokens = tokenize(draft);
	const issues: ValidationIssue[] = [];

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

	if (directiveName) {
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
	if (directiveName) {
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
			i.type === 'conflict' || i.type === 'missing-draw-folder' || i.type === 'missing-folder'
	);

	return { issues, locked };
}
