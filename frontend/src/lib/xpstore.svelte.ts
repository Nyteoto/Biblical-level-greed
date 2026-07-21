import type { Xp } from '$lib/api';

/** The latest XP, shared with the navbar.
 *
 * The bar lives in the header now, but the header does not fetch: every page
 * already pulls the dashboard, so they hand the result over instead of a second
 * request racing the first. Whoever loaded most recently wins, which is right —
 * there is only one number.
 */
export const xpState = $state<{ xp: Xp | null }>({ xp: null });

export function setXp(xp: Xp | undefined | null) {
	if (xp) xpState.xp = xp;
}
