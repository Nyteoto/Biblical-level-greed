/**
 * Move a node out of the app and onto `document.body`.
 *
 * There is one reason this exists, and it is worth stating so nobody deletes it
 * as ceremony: **the screen's curve is a CSS filter, and a filter rasterises
 * everything inside it.** The wrapper around `main` bends the whole app, which
 * is the intent — except for the lightbox, where the thing on screen is the
 * user's own photograph shown at full size. A photograph is not chrome. It does
 * not get curved, scanlined, vignetted or tinted, and there is no way to undo a
 * filter from inside it: the subtree is already a bitmap by then.
 *
 * So the lightbox leaves. `use:portal` relocates the element to the end of
 * `<body>`, outside both the filtered wrapper and the glass, where it draws at
 * its own z-index over everything and is treated by nothing.
 *
 * Svelte keeps owning the node — it is only reparented, not recreated — so
 * props, events and teardown all behave normally. The action puts it back on
 * destroy so Svelte's own cleanup finds it where it expects.
 */
export function portal(node: HTMLElement) {
	const origin = node.parentNode;
	document.body.appendChild(node);

	return {
		destroy() {
			// Svelte removes the node itself; this only matters if the element is
			// still around, which happens when the whole tree is torn down at once.
			if (node.parentNode === document.body && origin) origin.appendChild(node);
		}
	};
}
