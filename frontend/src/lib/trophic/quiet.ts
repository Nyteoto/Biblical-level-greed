// Which tags go quiet on this screen.
//
// Inside phosphor's album every line began `<phosphor>`, set in the same bold
// white as every other tag — so the one word that told you nothing on that
// screen was the loudest thing in each line. It is the subject, and the
// subject bar already says it. The tags that point at the folder being read
// are drawn dim and at the prose's weight; every other tag stays lit, because
// a line that also mentions `<garden>` is saying something this screen does
// not already know.
//
// A context rather than a prop, because the lines are drawn four components
// down — `PageDeck`, `DayPage`, then `TodoEntryText` or `ReplyBubble` — and
// none of the middle layers has any business knowing which folder is open.
// It is a getter so the lens can change subject without re-mounting the deck.
//
// Drawing only. The raw line is untouched and the tag still files exactly
// where it did, which is the same promise lifting makes.

import { getContext, setContext } from 'svelte';

const KEY = Symbol('quiet-tags');

/** Call in a lens: the tags that point at the folder it is showing. */
export function quietTags(tags: () => readonly string[]): void {
	setContext(KEY, tags);
}

/** What `ColorizedText` asks. Empty outside a lens that set it. */
export function isQuiet(): (tag: string) => boolean {
	const tags = getContext<(() => readonly string[]) | undefined>(KEY);
	return (tag) => !!tags && tags().includes(tag);
}
