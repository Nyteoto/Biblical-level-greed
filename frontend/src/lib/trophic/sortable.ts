/**
 * Rearranging a list by holding a row and dragging it.
 *
 * The gesture is deliberately the one this app already has. `HoldRing` runs a
 * corpus-pinned long press everywhere — 500ms stationary, 10px of slack — and
 * fires `trophic:hold` while the finger is *still down*. That last part is what
 * makes this possible without inventing a second gesture: the hold is the pick
 * up, and what happens next decides which of the two things you meant.
 *
 *   - Let go without moving, and it was a plain hold: the row's panel opens,
 *     exactly as it did before any of this existed.
 *   - Move, and the row is in your hand until you let go.
 *
 * So one gesture keeps two meanings and neither had to be discovered twice.
 * The cost is that the panel now opens on *release* rather than the instant the
 * ring closes, which is the honest ordering anyway: until you let go, the app
 * genuinely does not know which you meant.
 *
 * ## Why the geometry is read from the DOM
 *
 * A sortable list is a handful of headings that are already on screen, and
 * their positions are a fact the browser is holding. Mirroring them into state
 * would mean keeping that mirror true through a collapse, a scroll and a
 * window resize; reading them at pick-up costs one pass over half a dozen
 * elements and cannot be stale.
 *
 * The two decisions that are not about the DOM — where a drop lands, and what
 * the list looks like afterwards — are the pure pair below, so `verify:ui` can
 * hold them to an answer.
 */

/** One row's vertical extent, in the order the rows are drawn. */
export type Slot = { key: string; top: number; bottom: number };

/**
 * Which row a drop at `y` lands in front of, or `null` for the end of the
 * list.
 *
 * Halves, not edges: past the middle of a row you are asking to be below it.
 * Anything above the first row lands at the front, which is what a list
 * dragged off its own top edge should do rather than nothing.
 */
export function dropBefore(slots: Slot[], y: number): string | null {
	for (const slot of slots) {
		if (y < (slot.top + slot.bottom) / 2) return slot.key;
	}
	return null;
}

/**
 * `order` with `key` moved in front of `before`, or to the end when `before`
 * is null.
 *
 * Dropping a row on itself is not a move, and neither is dropping it in front
 * of the row it is already in front of — both return the order unchanged, so a
 * drag that goes nowhere writes nothing.
 */
export function moveBefore(order: string[], key: string, before: string | null): string[] {
	if (!order.includes(key) || before === key) return order;
	const rest = order.filter((k) => k !== key);
	if (before === null) {
		if (order[order.length - 1] === key) return order;
		return [...rest, key];
	}
	const at = rest.indexOf(before);
	if (at === -1) return order;
	const next = [...rest.slice(0, at), key, ...rest.slice(at)];
	return next.every((name, i) => name === order[i]) ? order : next;
}

export type SortParams = {
	/** This row's identity in the order. For a shelf group, its name. */
	key: string;
	/** Which list it belongs to. Rows find their siblings by it, so two
	 *  sortable lists on one screen cannot pick each other up. */
	list: string;
	/** The hold landed and the finger never moved. The plain hold. */
	onhold?: (x: number, y: number) => void;
	/** The row has been picked up. */
	onpick?: () => void;
	/** Dragging: this is where it would land right now. */
	onover?: (before: string | null) => void;
	/** Let go. `before` is the row it landed in front of, or null for the end. */
	ondrop?: (before: string | null) => void;
	/** Picked up and put down again with nothing moved, or cancelled. */
	oncancel?: () => void;
};

/** How far the finger travels before a hold becomes a drag. Smaller than the
 *  press's own 10px of slack on purpose: by the time this is armed the press
 *  has already happened, and what is being measured is intent to move rather
 *  than a hand that will not keep still. */
const DRAG_MIN = 5;

export function sortable(node: HTMLElement, params: SortParams) {
	let current = params;
	let origin: { x: number; y: number } | null = null;
	let slots: Slot[] = [];
	let dragging = false;
	let before: string | null = null;
	/** Exactly one click is eaten after a hold fires, whichever way it ended.
	 *  The same rule `LongPress` keeps, and for the same reason: the row is a
	 *  link or a button, and a hold that also followed the link — or folded the
	 *  heading it just opened a panel for — is one gesture doing two things. */
	let swallow = false;

	const measure = (): Slot[] => {
		const root = node.closest(`[data-sort-list="${current.list}"]`) ?? document;
		return Array.from(
			root.querySelectorAll<HTMLElement>(`[data-sort-key][data-sort="${current.list}"]`)
		).map((el) => {
			const box = el.getBoundingClientRect();
			return { key: el.dataset.sortKey ?? '', top: box.top, bottom: box.bottom };
		});
	};

	function moved(x: number, y: number) {
		if (!origin) return;
		if (!dragging && Math.hypot(x - origin.x, y - origin.y) <= DRAG_MIN) return;
		if (!dragging) {
			dragging = true;
			// Measured at the first movement rather than at the hold: a list
			// that animates the picked row would otherwise be measured
			// mid-animation.
			slots = measure();
			current.onpick?.();
		}
		const next = dropBefore(slots, y);
		if (next !== before) {
			before = next;
			current.onover?.(before);
		}
	}

	function release(x: number, y: number) {
		const wasDragging = dragging;
		const landed = before;
		swallow = true;
		disarm();
		if (wasDragging) current.ondrop?.(landed);
		else current.onhold?.(x, y);
	}

	function onMouseMove(e: MouseEvent) {
		moved(e.clientX, e.clientY);
	}
	function onMouseUp(e: MouseEvent) {
		release(e.clientX, e.clientY);
	}
	function onTouchMove(e: TouchEvent) {
		const touch = e.touches[0];
		if (!touch) return;
		// Not passive, and this is why: the page would otherwise scroll under a
		// row that is supposed to be in the reader's hand. Safe to refuse here
		// because the finger has already been stationary for the length of a
		// long press, so no scroll has begun.
		if (dragging) e.preventDefault();
		moved(touch.clientX, touch.clientY);
	}
	function onTouchEnd(e: TouchEvent) {
		const touch = e.changedTouches[0];
		release(touch?.clientX ?? 0, touch?.clientY ?? 0);
	}
	function onKey(e: KeyboardEvent) {
		if (e.key === 'Escape') {
			const was = dragging;
			disarm();
			if (was) current.oncancel?.();
		}
	}
	/** A heading is a button and a sidebar row is a link, and both would
	 *  otherwise start a native drag the moment the pointer moves. */
	function onDragStart(e: Event) {
		e.preventDefault();
	}

	function arm(x: number, y: number) {
		origin = { x, y };
		dragging = false;
		before = null;
		document.addEventListener('mousemove', onMouseMove, true);
		document.addEventListener('mouseup', onMouseUp, true);
		document.addEventListener('touchmove', onTouchMove, { passive: false, capture: true });
		document.addEventListener('touchend', onTouchEnd, true);
		document.addEventListener('touchcancel', onTouchEnd, true);
		document.addEventListener('keydown', onKey, true);
		document.addEventListener('dragstart', onDragStart, true);
	}

	function disarm() {
		origin = null;
		dragging = false;
		before = null;
		slots = [];
		document.removeEventListener('mousemove', onMouseMove, true);
		document.removeEventListener('mouseup', onMouseUp, true);
		document.removeEventListener('touchmove', onTouchMove, true);
		document.removeEventListener('touchend', onTouchEnd, true);
		document.removeEventListener('touchcancel', onTouchEnd, true);
		document.removeEventListener('keydown', onKey, true);
		document.removeEventListener('dragstart', onDragStart, true);
	}

	// The same claim `hold` makes, for the same reason: the ring is
	// watching this return value and will draw its refusal × over a hold that
	// nothing answered.
	const onHold = (event: Event) => {
		const detail = (event as CustomEvent<{ x: number; y: number }>).detail;
		event.preventDefault();
		event.stopPropagation();
		arm(detail.x, detail.y);
	};

	// A click is swallowed after a drag: the row is a link or a button, and
	// letting go over a different heading must not also open it.
	const onClick = (event: MouseEvent) => {
		if (!swallow) return;
		swallow = false;
		event.preventDefault();
		event.stopPropagation();
	};

	node.addEventListener('trophic:hold', onHold);
	node.addEventListener('click', onClick, true);
	node.setAttribute('data-hold', '');
	node.setAttribute('data-sort', params.list);
	node.setAttribute('data-sort-key', params.key);

	return {
		update(next: SortParams) {
			current = next;
			node.setAttribute('data-sort', next.list);
			node.setAttribute('data-sort-key', next.key);
		},
		destroy() {
			disarm();
			node.removeEventListener('trophic:hold', onHold);
			node.removeEventListener('click', onClick, true);
			node.removeAttribute('data-hold');
			node.removeAttribute('data-sort');
			node.removeAttribute('data-sort-key');
		}
	};
}
