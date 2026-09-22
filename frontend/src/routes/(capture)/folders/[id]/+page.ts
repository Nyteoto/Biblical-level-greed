/**
 * Where the album screen used to live.
 *
 * A folder stopped being *where you are* and became what every lens is a
 * question about, so this route's whole job is to carry an old link into the
 * new shape — the PWA icons on two home screens, anything bookmarked, and the
 * `?entry=` deep links the banner has been minting for months.
 *
 * Everything after the id is handed through untouched: `year`, `month`,
 * `chapter`, `day` and `entry` all mean on the Log lens exactly what they
 * meant here.
 */
import { redirect } from '@sveltejs/kit';
import { lensHref } from '$lib/trophic/scope';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ params, url }) => {
	const extra: Record<string, string> = {};
	for (const key of ['month', 'chapter', 'day', 'entry']) {
		const value = url.searchParams.get(key);
		if (value) extra[key] = value;
	}
	redirect(
		308,
		lensHref(
			'/log',
			{ folder: params.id, year: url.searchParams.get('year') ?? undefined },
			extra
		)
	);
};
