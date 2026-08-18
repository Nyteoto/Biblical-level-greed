/**
 * Mark a node as answering a hold, and claim the gesture when it lands.
 *
 * `HoldRing` runs the hold globally and dispatches a cancelable `trophic:hold`
 * on whatever was under the finger. Claiming it means two things at once —
 * "open my panel" and "do not draw the null ×" — and both have to happen or the
 * ring reports that a hold nothing answered has just been answered.
 *
 * It exists as an action rather than as three lines in each component because
 * there are two card surfaces for the same folder and they must not drift. The
 * `data-hold` attribute is not styled; it says in the DOM that this node has
 * properties, which is what makes the behaviour findable from the outside.
 */
export function holdable(node: HTMLElement, onhold: (x: number, y: number) => void) {
	let handler = onhold;

	const fire = (event: Event) => {
		const detail = (event as CustomEvent<{ x: number; y: number }>).detail;
		// Claim it. The ring is watching this exact return value.
		event.preventDefault();
		event.stopPropagation();
		handler(detail.x, detail.y);
	};

	node.addEventListener('trophic:hold', fire);
	node.setAttribute('data-hold', '');

	return {
		update(next: (x: number, y: number) => void) {
			handler = next;
		},
		destroy() {
			node.removeEventListener('trophic:hold', fire);
			node.removeAttribute('data-hold');
		}
	};
}
