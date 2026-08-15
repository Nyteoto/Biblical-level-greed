// What shape is this device, and where is the keyboard.
//
// Ported from `hooks/useDeviceType.ts`, `hooks/useVirtualKeyboard.ts` and
// `hooks/useHandMode.ts` — three hooks in one file because they answer one
// question between them, and pinned together by `viewport.json` (23 cases).
// The classification functions are pure and take their environment as an
// argument; the reactive wrappers underneath read the real one.
//
// Every rule below is a workaround for a specific lie the platform tells:
//
//   - **iPadOS 13+ reports a Macintosh user agent.** The only thing that
//     separates an iPad from a MacBook is that the iPad has touch points.
//   - **`isMobile` needs both the UA flags and the media query.** The query
//     catches Android tablets that send a desktop UA; the flags catch the
//     devices where the query itself lies. A Windows touchscreen laptop
//     answers yes to touch and no to the query, and is not mobile.
//   - **The keyboard test is 150px absolute, strictly greater.** A ratio test
//     (`height < 0.75`) is wrong twice: it misses Android floating keyboards,
//     which take under a quarter of the screen, and it fires when Chrome's
//     address bar hides on scroll.
//   - **Hand mode is validated on read.** localStorage is user-writable, and
//     anything that is not one of the two known strings falls back to right —
//     a port that trusts it renders a broken layout.

export type DeviceType = {
	isIPhone: boolean;
	isIPad: boolean;
	isAndroid: boolean;
	isMobile: boolean;
};

export type HandMode = 'left' | 'right';

export const COARSE_QUERY = '(pointer: coarse) and (hover: none)';
/** Viewport shrinkage that counts as an on-screen keyboard. */
export const KEYBOARD_THRESHOLD = 150;
const HAND_KEY = 'trophic-hand-mode';

export function classifyDevice(
	userAgent: string,
	maxTouchPoints: number,
	coarsePointer: boolean
): DeviceType {
	const isIPhone = /iPhone/.test(userAgent);
	const isIPad = /iPad/.test(userAgent) || (/Macintosh/.test(userAgent) && maxTouchPoints > 1);
	const isAndroid = /Android/.test(userAgent);
	return {
		isIPhone,
		isIPad,
		isAndroid,
		isMobile: isIPhone || isIPad || isAndroid || coarsePointer
	};
}

export function keyboardOpen(
	innerHeight: number,
	visualViewportHeight: number | null
): boolean {
	// No visualViewport means false, permanently. Desktop and an iPad with an
	// external keyboard both land here, and both are right.
	if (visualViewportHeight == null) return false;
	return innerHeight - visualViewportHeight > KEYBOARD_THRESHOLD;
}

export function readHandMode(stored: string | null): HandMode {
	return stored === 'left' || stored === 'right' ? stored : 'right';
}

/** Device shape, read once: none of it changes without a reload. */
export function deviceType(): DeviceType {
	if (typeof window === 'undefined') {
		return { isIPhone: false, isIPad: false, isAndroid: false, isMobile: false };
	}
	return classifyDevice(
		navigator.userAgent,
		navigator.maxTouchPoints ?? 0,
		window.matchMedia(COARSE_QUERY).matches
	);
}
