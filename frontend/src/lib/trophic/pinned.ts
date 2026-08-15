// The pure half of the pin: what a pinned folder does to a line on the way
// out. Split from `pinned.svelte.ts` for the reason `device.ts` is — runes
// only compile in a `.svelte.ts`, and the rule below is worth being able to
// replay outside a browser.
//
// **The tag is written into the raw text, not carried beside it.** That is the
// whole design of the pin, and it is not the obvious choice: the obvious one is
// to send the folder id along with the capture and file the entry server-side.
// It would be wrong here. The log stores what was typed and derives everything
// else from it, so a folder carried in a side channel would be a second kind of
// membership that no rebuild could reproduce. Written into the line, a pinned
// capture is indistinguishable from one you tagged by hand — visible while you
// write it, visible in the log afterwards, and still true after `rebuild()`.
//
// A folder claims `normalize_tag(name)` when it is created, so the tag a pin
// appends is guaranteed to resolve back to it.

import { tokenize } from './tokenize';

/**
 * The line as it should be sent, given the pinned folder's tag.
 *
 * Nothing is appended when the line already reaches that folder — by `<tag>`
 * or by the `--tag` directive, which are the same thing to the parser. Typing
 * the tag yourself with a pin on must not produce it twice.
 */
export function withPinnedTag(text: string, tag: string): string {
	if (!tag) return text;
	const wanted = tag.toLowerCase();
	for (const token of tokenize(text)) {
		if ((token.kind === 'folder' || token.kind === 'directive') && token.value === wanted) {
			return text;
		}
	}
	// Media with no words is still a capture, and it still belongs in the
	// folder — the tag becomes the whole line.
	const body = text.trimEnd();
	return body ? `${body} <${tag}>` : `<${tag}>`;
}

/**
 * Which tag a pin on this folder should write.
 *
 * Its own name, normalised the way `parser.normalize_tag` does it — trimmed
 * and lowercased, spaces kept, because that is the tag a folder claims when it
 * is created. If something else had already claimed that tag the folder never
 * got it, so fall back to whatever does point here. Null means nothing does,
 * and a folder no tag reaches cannot be pinned: the line would be written and
 * land nowhere, which is worse than refusing the pin.
 */
export function tagForPin(folder: { name: string; tags: string[] }): string | null {
	const own = folder.name.trim().toLowerCase();
	if (folder.tags.includes(own)) return own;
	return folder.tags[0] ?? null;
}
