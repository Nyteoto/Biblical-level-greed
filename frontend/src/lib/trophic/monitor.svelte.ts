/**
 * The monitor's own controls: how strong the glass is, and whether it is there.
 *
 * Six `--crt-*` custom properties are the entire effect — `app.css` and
 * `+layout.svelte` read nothing else — so making the monitor adjustable is a
 * question of who owns those six numbers, not of rewriting any of it. They live
 * here, and the layout writes them onto `:root` in one effect. Nothing about the
 * glass moves down into a component, which is the rule the whole treatment was
 * built around.
 *
 * `sheen` is where `curve` used to be. The curve was a real barrel distortion
 * and cost 23ms of every frame; it is now suggested with static paint, and this
 * dial scales the impression. That it is an ordinary custom property like the
 * other five is the simplification: the curve had to be special-cased here,
 * because it was a filter's `scale` rather than anything CSS could inherit.
 *
 * **`off` is not "all six at zero".** Seven full-viewport layers that paint
 * nothing are still seven layers to composite, so a switch that only zeroed the
 * numbers would keep paying for a monitor nobody can see. Off takes them out of
 * the document; the numbers are kept, so turning it back on returns the screen
 * you had rather than the one that shipped.
 *
 * Same rule as `settings.svelte.ts`, and worth restating: **nothing here is a
 * fact about what you wrote.** These change how the app is lit on this machine
 * and touch no stored byte, which is why `localStorage` is the right home and
 * the log is not.
 */

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
	sheen: 1
};

export type MonitorKey = keyof typeof MONITOR_DEFAULTS;

/** How each number is spelled as a CSS value. Every one of them is a custom
 *  property now, so there is no longer an exception to carry. */
const PROPS: Record<MonitorKey, (value: number) => string> = {
	scanAlpha: (v) => `${v}`,
	scanPeriod: (v) => `${v}px`,
	vignette: (v) => `${v}`,
	grain: (v) => `${v}`,
	bloom: (v) => `${v}`,
	sheen: (v) => `${v}`
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
	sheen = $state(MONITOR_DEFAULTS.sheen);

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
