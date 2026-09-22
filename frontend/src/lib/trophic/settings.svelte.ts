/**
 * The three switches on the Settings screen that change how the Log behaves.
 *
 * They live in `localStorage` rather than in the log, and that is the rule
 * worth stating: **nothing here is a fact about what you wrote.** Whether
 * albums restart each year changes how the same entries are grouped on the way
 * out; it does not change a single stored byte, and turning it off has to give
 * back exactly the shelf you would have had if it had never been on. Anything
 * that fails that test is not a setting, it is a migration wearing one.
 *
 * A module-level rune rather than a store per screen: the Log reads all three
 * and Settings writes all three, and two copies of a boolean is one more thing
 * that can disagree. `.svelte.ts` because `$state` in a plain `.ts` is an
 * undefined call at runtime and renders a blank page — see `device.svelte.ts`,
 * which learnt that the hard way.
 */

/** Which screen `/log` opens on. `latest` goes straight into the album you
 *  wrote in most recently, which is the right default for someone deep in one
 *  project and the wrong one for someone with six. Hence the choice. */
export type OpenOn = 'shelf' | 'latest';

const KEYS = {
	openOn: 'log-open-on',
	yearAlbums: 'log-year-albums'
} as const;

function read(key: string, fallback: string): string {
	try {
		return localStorage.getItem(key) ?? fallback;
	} catch {
		// Private mode, or storage turned off. The defaults are good defaults.
		return fallback;
	}
}

function write(key: string, value: string) {
	try {
		localStorage.setItem(key, value);
	} catch {
		/* the setting simply does not persist; the screen still works */
	}
}

class LogSettings {
	// SSR runs this too, and there is no localStorage there. The defaults are
	// what renders on the server; `hydrate()` reconciles on the client, which
	// is a frame later and invisible.
	openOn = $state<OpenOn>('shelf');
	yearAlbums = $state(true);

	hydrate() {
		this.openOn = read(KEYS.openOn, 'shelf') === 'latest' ? 'latest' : 'shelf';
		this.yearAlbums = read(KEYS.yearAlbums, '1') === '1';
	}

	setOpenOn(value: OpenOn) {
		this.openOn = value;
		write(KEYS.openOn, value);
	}

	setYearAlbums(value: boolean) {
		this.yearAlbums = value;
		write(KEYS.yearAlbums, value ? '1' : '0');
	}
}

export const logSettings = new LogSettings();

/** Which timezone the day boundary is drawn on, spelled the way the Settings
 *  row shows it. Read from the browser rather than configured: the backend
 *  computes `day` in the user's zone and this is the same zone by construction,
 *  so a control here would only be a way to make the two disagree. */
export function dayBoundary(): string {
	const minutes = -new Date().getTimezoneOffset();
	const sign = minutes < 0 ? '-' : '+';
	const hours = Math.floor(Math.abs(minutes) / 60);
	const rest = Math.abs(minutes) % 60;
	return `00:00 GMT${sign}${hours}${rest ? `:${String(rest).padStart(2, '0')}` : ''}`;
}
