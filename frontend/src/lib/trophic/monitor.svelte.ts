/**
 * The monitor's own controls: how strong the glass is, and whether it is there.
 *
 * The five `--crt-*` custom properties and the curve's corner displacement are
 * the entire effect — `app.css` and `+layout.svelte` read nothing else — so
 * making the monitor adjustable is a question of who owns those six numbers,
 * not of rewriting any of it. They live here, and the layout writes them onto
 * `:root` in one effect. Nothing about the glass moves down into a component,
 * which is the rule the whole treatment was built around.
 *
 * **`off` is not "all six at zero".** A CSS filter rasterises its subtree
 * whatever its scale, and becomes the containing block for `fixed` descendants
 * inside it, so a switch that only zeroed the numbers would keep paying for a
 * monitor nobody can see. Off takes the four layers and the filter out of the
 * document; the numbers are kept, so turning it back on returns the screen you
 * had rather than the one that shipped.
 *
 * Same rule as `settings.svelte.ts`, and worth restating: **nothing here is a
 * fact about what you wrote.** These change how the app is lit on this machine
 * and touch no stored byte, which is why `localStorage` is the right home and
 * the log is not.
 */

import { CORNER_PX } from './crt';

/**
 * The settled defaults, which are the same numbers `:root` carries in
 * `app.css`. The duplication is deliberate and one-directional: the stylesheet
 * is what paints during SSR and before hydration, so it has to stand alone, and
 * this side has to agree with it or "Reset" would hand back a screen the app
 * never opens on. If you retune one, retune the other.
 */
export const MONITOR_DEFAULTS = {
	scanAlpha: 0.07,
	scanPeriod: 3,
	vignette: 0.4,
	grain: 0.02,
	bloom: 1,
	curve: CORNER_PX
};

export type MonitorKey = keyof typeof MONITOR_DEFAULTS;

/** Which custom property each number is written to. `curve` is absent on
 *  purpose — it is not a paint, it is the filter's `scale`, and the layout
 *  passes it through `barrelScale()` rather than through CSS. */
const PROPS: Partial<Record<MonitorKey, (value: number) => string>> = {
	scanAlpha: (v) => `${v}`,
	scanPeriod: (v) => `${v}px`,
	vignette: (v) => `${v}`,
	grain: (v) => `${v}`,
	bloom: (v) => `${v}`
};

const KEY_PREFIX = 'crt-';

function read(key: string, fallback: number): number {
	try {
		const raw = localStorage.getItem(KEY_PREFIX + key);
		if (raw === null) return fallback;
		const value = Number(raw);
		// A hand-edited or half-written entry should not be able to blank the
		// screen; an unreadable number is no number at all.
		return Number.isFinite(value) ? value : fallback;
	} catch {
		// Private mode, or storage turned off. The defaults are good defaults.
		return fallback;
	}
}

function write(key: string, value: string) {
	try {
		localStorage.setItem(KEY_PREFIX + key, value);
	} catch {
		/* the setting simply does not persist; the screen still works */
	}
}

class Monitor {
	// SSR runs this too, and there is no localStorage there. What renders on the
	// server is the stylesheet's own defaults, which these mirror; `hydrate()`
	// reconciles on the client a frame later.
	on = $state(true);
	scanAlpha = $state(MONITOR_DEFAULTS.scanAlpha);
	scanPeriod = $state(MONITOR_DEFAULTS.scanPeriod);
	vignette = $state(MONITOR_DEFAULTS.vignette);
	grain = $state(MONITOR_DEFAULTS.grain);
	bloom = $state(MONITOR_DEFAULTS.bloom);
	curve = $state(MONITOR_DEFAULTS.curve);

	hydrate() {
		this.on = read('on', 1) === 1;
		for (const key of Object.keys(MONITOR_DEFAULTS) as MonitorKey[]) {
			this[key] = read(key, MONITOR_DEFAULTS[key]);
		}
	}

	set(key: MonitorKey, value: number) {
		this[key] = value;
		write(key, String(value));
	}

	setOn(value: boolean) {
		this.on = value;
		write('on', value ? '1' : '0');
	}

	reset() {
		for (const key of Object.keys(MONITOR_DEFAULTS) as MonitorKey[]) {
			this.set(key, MONITOR_DEFAULTS[key]);
		}
	}

	/** True when every number is already where it shipped, so the screen can
	 *  say so instead of offering a reset that would do nothing. */
	get isDefault(): boolean {
		return (Object.keys(MONITOR_DEFAULTS) as MonitorKey[]).every(
			(key) => this[key] === MONITOR_DEFAULTS[key]
		);
	}

	/**
	 * The custom properties, as the layout should write them.
	 *
	 * Off zeroes them rather than leaving the last values behind. The layers are
	 * gone by then and nothing reads most of these — but the bloom is a
	 * `text-shadow` inherited from `body`, not a layer, and it is the one that
	 * would otherwise survive the switch being off.
	 */
	get vars(): Record<string, string> {
		const out: Record<string, string> = {};
		for (const [key, format] of Object.entries(PROPS) as [
			MonitorKey,
			(value: number) => string
		][]) {
			out[`--crt-${kebab(key)}`] = this.on ? format(this[key]) : format(0);
		}
		return out;
	}
}

function kebab(key: string): string {
	return key.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`);
}

export const monitor = new Monitor();
