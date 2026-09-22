/**
 * The subject every lens is a question about.
 *
 * The rail does not change *where you are*; it changes *what is being asked*
 * about one selection — a folder, through a year. That selection is this, and
 * it survives every switch between Map, Log, Threads and Record. It is the
 * whole architecture of the navigation, and it fits in nine lines.
 *
 * **It lives in the URL and is stored nowhere.** Two reasons, and the second is
 * the one that matters:
 *
 *   - every state in the app is then a link you can send yourself, land on
 *     from the banner, or reload into;
 *   - a scope held in a store would be a second source of truth about which
 *     folder you are reading, and the app already has one — the address bar.
 *     Two of them is how a back button starts lying.
 *
 * The year is a string rather than a number because `all` is one of its
 * values: "do not cut by year" is a real answer and not an absent one, which
 * is the same shape `_year()` uses on the server.
 */

export type Scope = {
	/** A folder id, `unfiled` for the pile nothing has claimed, or `null` for
	 *  every folder at once. */
	folder: string | null;
	/** `YYYY`, or `all`. */
	year: string;
};

/** The year a bare URL means: this one. */
export const thisYear = () => String(new Date().getFullYear());

export function readScope(url: URL): Scope {
	return {
		folder: url.searchParams.get('folder') || null,
		year: url.searchParams.get('year') || thisYear()
	};
}

/**
 * A link to `path` carrying the scope, plus whatever else the caller names.
 *
 * Defaults are left out rather than spelled: a URL that says `?year=2026` in
 * 2026 is noise, and one that says `?folder=` says something false. What comes
 * back is the shortest link that means what was asked.
 */
export function lensHref(
	path: string,
	scope: Partial<Scope>,
	extra: Record<string, string | number | null | undefined> = {}
): string {
	const q = new URLSearchParams();
	if (scope.folder) q.set('folder', scope.folder);
	if (scope.year && scope.year !== thisYear()) q.set('year', scope.year);
	for (const [k, v] of Object.entries(extra)) {
		if (v !== null && v !== undefined && v !== '') q.set(k, String(v));
	}
	const s = q.toString();
	return s ? `${path}?${s}` : path;
}
