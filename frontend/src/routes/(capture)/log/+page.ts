/**
 * Where `/log` actually goes, decided before anything is drawn.
 *
 * `Opens on: latest day` used to be an effect inside the page: the shelf
 * rendered, its data arrived, and *then* the jump fired. That is a visible
 * hiccup — you saw the year shelf, read it for a frame, and were moved. The
 * redirect belongs here instead, because a `load` runs before the component
 * exists and SvelteKit never paints a page it is redirecting away from.
 *
 * It costs one shelf request that the album screen will not reuse. That is the
 * price of knowing where to go before going there, and it is the same request
 * the page was making anyway — when no redirect happens it is handed to the
 * component through `data`, so nothing is fetched twice.
 *
 * `?shelf` is how the year shelf stays reachable. Without it, `latest` would
 * make the shelf a place you can never be: every arrival bounces, and the
 * bounce uses `replaceState`, so back does not help either. The nav pill's Log
 * button sets it — see `TabPill.svelte`.
 */
import { redirect } from '@sveltejs/kit';
import { getShelf } from '$lib/trophic/api';
import { logSettings } from '$lib/trophic/settings.svelte';
import type { PageLoad } from './$types';

export const load: PageLoad = async ({ url }) => {
	// `ssr = false` at the root, so this only ever runs in the browser and
	// `localStorage` is really there.
	logSettings.hydrate();

	if (url.searchParams.has('shelf') || logSettings.openOn !== 'latest') return {};

	const key = logSettings.yearAlbums ? String(new Date().getFullYear()) : 'all';
	let shelf;
	try {
		shelf = await getShelf(key);
	} catch {
		// The shelf will report the failure itself once it renders. A backend
		// that is down is not a reason to refuse to draw the page.
		return {};
	}

	// `latest` is the answer; the rest is for a server older than this file,
	// which returns nothing for it. Staying put in silence is the failure this
	// setting already had once.
	const target = shelf.latest
		? (shelf.latest.folder ?? 'unfiled')
		: (shelf.albums[0]?.id ?? (shelf.unfiled > 0 ? 'unfiled' : null));

	if (target) redirect(307, `/folders/${target}?year=${shelf.year ?? 'all'}`);

	// Nothing to open — a year with no entries at all. Hand the shelf over
	// rather than making the page ask for it again.
	return { shelf, key };
};
