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
