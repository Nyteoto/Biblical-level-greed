/**
 * How a shelf reads: which albums are loose, which sit under a heading, and
 * where an album's link goes.
 *
 * Why it is shaped this way
 * -------------------------
 * There are two screens showing the shelf and they are not the same screen —
 * the year shelf draws cards in a grid, the album sidebar draws rows in a rail
 * — but they are showing the same object, and CLAUDE.md already says so:
 * dragging a heading on either "is the same act, and neither screen owns it".
 * They agreed about that by both spelling it out. The same two-line split, the
 * same drop rule, and `albumHref` written three times across the two of them
 * and the album page, with the third differing in its year fallback.
 *
 * Nothing here touches the DOM, so the markup stays where it belongs — a rail
 * row and a grid card have no business being one component. What is shared is
 * the *reading*: given a shelf, what is in each part of it.
 *
 * Nothing here is stored either. A group is an arrangement of a year, and the
 * all-years shelf has no groups at all — which falls out of `groups` being
 * empty rather than being a case anyone has to write.
 */
import { lensHref } from './scope';

import type { Album, Shelf } from './api';
import { moveBefore } from './sortable';

export type Section = { name: string; albums: Album[] };

/**
 * The shelf in two parts: what has no group, then the named groups in the
 * shelf's own order — first named, first drawn.
 *
 * Ungrouped stays on top and keeps the plain list, so a shelf nobody has
 * arranged looks exactly as it did before groups existed. Nothing is gained by
 * making you scroll past an empty ceremonial heading to reach your folders.
 *
 * A heading with nothing under it is kept rather than dropped: an empty group
 * is a place you have made and not filled yet, and a shelf that silently
 * deleted it the moment you dragged its last album out would be taking a
 * decision back on your behalf.
 */
export function splitShelf(shelf: Shelf | null): { loose: Album[]; sections: Section[] } {
	const albums = shelf?.albums ?? [];
	return {
		loose: albums.filter((a) => !a.group),
		sections: (shelf?.groups ?? []).map((name) => ({
			name,
			albums: albums.filter((a) => a.group === name)
		}))
	};
}

/** Where an album opens. `null` is the unfiled pile, which is an album you can
 *  open like any other and is not a folder. */
export function albumHref(folderId: string | null, year: string): string {
	return lensHref('/log', { folder: folderId ?? 'unfiled', year });
}

/**
 * The order a drop produces, or `null` when the drop changed nothing.
 *
 * `null` rather than the unchanged array because every caller has the same
 * next question — do I send this? — and answering it by comparing identity
 * with the array they passed in is the kind of thing that works until someone
 * copies it. See `order-groups` in eventlog.py for why the whole order goes
 * over the wire rather than a move.
 */
export function reorderGroups(
	groups: string[],
	name: string,
	before: string | null
): string[] | null {
	const next = moveBefore(groups, name, before);
	return next === groups ? null : next;
}
