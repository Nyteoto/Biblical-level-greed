import { redirect } from '@sveltejs/kit';

/**
 * `/tree` and every tree below it are hidden.
 *
 * A layout load rather than a page one, so `/tree/<domain>` is covered by the
 * same three lines as `/tree` — a redirect on the index only would leave every
 * deep link into a tree still rendering a screen the app no longer has a way
 * to reach.
 *
 * Hidden, not deleted: see `today/+page.ts` for why that distinction is being
 * kept, and what putting them back costs.
 */
export function load() {
	redirect(307, '/');
}
