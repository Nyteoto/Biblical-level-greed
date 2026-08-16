import { redirect } from '@sveltejs/kit';

/**
 * `/today` is hidden.
 *
 * The tech tree's two screens are out of the redesign's scope and out of the
 * shell's tab pill. They are *hidden*, not deleted: the page component, its
 * store and its API are all still here and still work, and taking this file
 * away is the whole of putting the screen back. That is deliberate — the
 * decision to remove the tech tree outright is a separate one, to be made with
 * evidence rather than as a side effect of a visual redesign.
 */
export function load() {
	redirect(307, '/');
}
