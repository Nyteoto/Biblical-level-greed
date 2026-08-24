/**
 * Answer a hold on this node. The one way anything in the app does that.
 *
 * `HoldRing` runs the gesture globally — the corpus-pinned `LongPress` state
 * machine, drawn where the finger is — and dispatches a cancelable
 * `trophic:hold` on whatever was under the point. This claims it, which means
 * three things at once: open my panel, do not draw the null ×, and eat the
 * click this press is about to produce.
 *
 * Why it is shaped this way
 * -------------------------
 * There used to be **two** hold mechanisms and they overlapped. `holdable`
 * claimed the global ring's gesture; `longpress` ran a *second* `LongPress`
 * timer per node, fired from that, and then claimed the ring's as well so the
 * × would not be drawn over its menu. Its own comment admitted the shape of
 * the problem: the two "cannot disagree about when a hold happened" only
 * because both were constructed with the same delay. `LeadDay` and `LightDay`
 * imported both and used them on different elements of the same card, and
 * `FolderAssignMenu` documented the collision rather than resolving it.
 *
 * They were also not the same gesture, which is the part that made merging
 * them a fix rather than a tidy-up. `longpress` opened on a desktop
 * right-click and swallowed the synthetic click that follows a fired press;
 * `holdable` did neither, so a hold on a photograph opened the panel *and*
 * let the click underneath through. Both behaviours are kept here, so every
 * hold in the app now works the way the assign menu's did.
 *
 * The `data-hold` attribute is not styled. It says in the DOM that this node
 * has properties, which is what makes the behaviour findable from the outside
 * — by a test, or by whoever next wonders why one hold opens a panel and
 * another draws an ×.
 */
export type HoldAt = (x: number, y: number) => void;

export function hold(node: HTMLElement, onhold: HoldAt) {
	let handler = onhold;
	// Set when a press fires, cleared by the one click that follows it.
	// Leaving it set would eat the user's next real tap.
	let fired = false;

	const claim = (event: Event) => {
		const detail = (event as CustomEvent<{ x: number; y: number }>).detail;
		// Claim it. The ring is watching this exact return value.
		event.preventDefault();
		event.stopPropagation();
		fired = true;
		handler(detail.x, detail.y);
	};

	const onClick = (event: MouseEvent) => {
		if (!fired) return;
		fired = false;
		event.preventDefault();
		event.stopPropagation();
	};

	// A hold and a right-click are the same request on a desk. `HoldRing`
	// refuses the browser's menu while a hold is live; this is what happens
	// when there was no hold, only the click.
	const onContextMenu = (event: MouseEvent) => {
		event.preventDefault();
		handler(event.clientX, event.clientY);
	};

	node.addEventListener('trophic:hold', claim);
	node.addEventListener('click', onClick, true);
	node.addEventListener('contextmenu', onContextMenu);
	node.setAttribute('data-hold', '');

	return {
		update(next: HoldAt) {
			handler = next;
		},
		destroy() {
			node.removeEventListener('trophic:hold', claim);
			node.removeEventListener('click', onClick, true);
			node.removeEventListener('contextmenu', onContextMenu);
			node.removeAttribute('data-hold');
		}
	};
}
