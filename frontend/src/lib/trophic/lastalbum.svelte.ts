/**
 * The album you were last reading, so the Log tab can put you back in it.
 *
 * This exists because the Log became two screens without a way between them.
 * The year shelf is an index and an album is the reading, and once
 * `Opens on: latest day` started skipping the index there was no route back to
 * it at all — the album sidebar prints the year as a heading, not a link, and
 * the redirect used `replaceState`, so the back button had nothing to return
 * to either. One control that flips between the two is the smallest fix, and
 * flipping needs somewhere to remember the other side.
 *
 * **It is navigation, not a setting.** Nothing here changes what the app shows
 * you, only which of two screens you land on next, so it lives in
 * `sessionStorage` rather than beside the switches in `settings.svelte.ts`:
 * being returned to last week's album because you closed the laptop is not a
 * kindness. A fresh session starts at the shelf, which is the honest default.
 */

const KEY = 'log-last-album';

export type LastAlbum = { id: string; year: string };

function read(): LastAlbum | null {
	try {
		const raw = sessionStorage.getItem(KEY);
		if (!raw) return null;
		const value = JSON.parse(raw);
		// A hand-edited or half-written entry must not be able to send the nav
		// pill somewhere that 404s.
		return typeof value?.id === 'string' && typeof value?.year === 'string' ? value : null;
	} catch {
		return null;
	}
}

class LastAlbumStore {
	// SSR is off app-wide, but this still starts empty and reconciles in
	// `hydrate()` so the value is read once rather than on every render.
	current = $state<LastAlbum | null>(null);

	hydrate() {
		this.current = read();
	}

	remember(id: string, year: string) {
		const next = { id, year };
		this.current = next;
		try {
			sessionStorage.setItem(KEY, JSON.stringify(next));
		} catch {
			/* the toggle simply has nothing to flip back to */
		}
	}

	/** Where the Log tab should go to *leave* the shelf, or null when there is
	 *  nowhere to go back to yet. */
	get href(): string | null {
		return this.current ? `/folders/${this.current.id}?year=${this.current.year}` : null;
	}
}

export const lastAlbum = new LastAlbumStore();
