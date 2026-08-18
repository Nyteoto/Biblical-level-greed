/**
 * Move a node out of the app and onto `document.body`.
 *
 * This existed for a reason that has since gone away, and it is worth writing
 * down which part survived. **The screen's curve used to be a CSS filter, and a
 * filter rasterises everything inside it** — including the lightbox, where the
 * thing on screen is the user's own photograph at full size. There was no way
 * to undo a filter from inside it; the subtree was already a bitmap. So the
 * lightbox left.
 *
 * The curve is now static paint and there is no filter to escape. What remains
 * is still worth escaping: the glass layers are `fixed` and sit at z-9000, and
 * a photograph must be above them rather than under a scanline. `use:portal`
 * relocates the element to the end of `<body>`, where it draws over everything
 * and is treated by nothing. Do not delete it as ceremony — `.crt-exempt` turns
 * the bloom off, and this is what puts the picture above the rest.
 *
 * Svelte keeps owning the node — it is only reparented, not recreated — so
 * props and events behave normally. **Teardown does not**, and that is the part
 * this file gets wrong if you let it.
 *
 * It used to put the node back where it came from on destroy, on the theory
 * that Svelte's own cleanup would then find it where it expected. It does not:
 * an `{#if}` block removes what is inside its anchors, and a node that has been
 * moved to `body` and then handed back is in neither place Svelte looks. The
 * result was a lightbox that survived being closed — reparented into
 * `main.crt-screen`, still `fixed inset-0`, still opaque, still covering the
 * whole screen, and now *inside* the very filter it portalled out of to escape.
 * The only ways out were a reload or a route change, which is exactly what
 * being stuck in a photo viewer feels like.
 *
 * So the action removes the node itself. Svelte may also try, and `remove()` on
 * an already-detached node is a no-op, so the two cannot fight.
 */
export function portal(node: HTMLElement) {
	document.body.appendChild(node);

	return {
		destroy() {
			node.remove();
		}
	};
}
