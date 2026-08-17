/**
 * Quantise a big display numeral to a block grid, so it reads as a bitmap font.
 *
 * Only the largest type gets this. Body text stays as the font drew it: the
 * whole point of the effect is the contrast between a chunky heading and the
 * crisp line under it, and pixelating both would just look like a low-resolution
 * screen rather than like a machine with one display face.
 *
 * **Why a canvas and not an SVG filter.** The textbook way to do this is a
 * filter chain — `feFlood` a one-pixel dot, `feComposite` it against the source,
 * `feTile` the result, `feMorphology` to fill. It renders nothing at all in
 * WebKit, which is the engine this app actually ships in (`desktop.py` points a
 * WebKitGTK window at it). Two variants were tried and both produced an empty
 * box. So: draw the text into a canvas at 1/n scale, then let CSS scale it back
 * up with nearest-neighbour.
 *
 * The alpha is hard-thresholded after the downsample. Without that the shrink is
 * antialiased and the result reads as a blur rather than as pixels — the edges
 * have to be hard for it to look deliberate.
 *
 * The element keeps its real text as `data-text` and gets an `aria-label`, so
 * what is on screen is a picture but what a screen reader gets is still the
 * year.
 */

type Options = {
	/** Block size in CSS pixels. 3 is "a tiny bit pixelated" at display sizes. */
	block?: number;
};

export function pixelate(node: HTMLElement, options: Options = {}) {
	const block = options.block ?? 3;
	const text = node.textContent?.trim() ?? '';
	if (!text) return {};

	node.setAttribute('data-text', text);
	node.setAttribute('aria-label', text);

	const canvas = document.createElement('canvas');
	canvas.style.display = 'block';
	canvas.style.imageRendering = 'pixelated';

	function draw() {
		const style = getComputedStyle(node);
		const size = parseFloat(style.fontSize);
		if (!size) return;

		const font = `${style.fontStyle} ${style.fontWeight} ${size}px ${style.fontFamily}`;
		const tracking = parseFloat(style.letterSpacing) || 0;

		const measure = canvas.getContext('2d');
		if (!measure) return;
		measure.font = font;
		if ('letterSpacing' in measure) measure.letterSpacing = `${tracking}px`;

		// Tight to the glyphs, measured rather than guessed from the font size.
		// It has to be tight because the canvas replaces a text node inside a
		// `items-baseline` row: a box with slack under the glyphs puts its own
		// bottom edge where the baseline should be and drops the line of metadata
		// beside it by that much.
		const metrics = measure.measureText(text);
		const ascent = Math.ceil(metrics.actualBoundingBoxAscent);
		const descent = Math.ceil(Math.max(0, metrics.actualBoundingBoxDescent));
		const width = Math.ceil(metrics.width + Math.abs(tracking));
		const height = ascent + descent;
		const w = Math.max(1, Math.round(width / block));
		const h = Math.max(1, Math.round(height / block));

		canvas.width = w;
		canvas.height = h;
		canvas.style.width = `${w * block}px`;
		canvas.style.height = `${h * block}px`;

		const ctx = canvas.getContext('2d');
		if (!ctx) return;
		ctx.setTransform(1, 0, 0, 1, 0, 0);
		ctx.clearRect(0, 0, w, h);
		ctx.scale(1 / block, 1 / block);
		ctx.font = font;
		if ('letterSpacing' in ctx) ctx.letterSpacing = `${tracking}px`;
		ctx.fillStyle = style.color;
		ctx.textBaseline = 'alphabetic';
		ctx.fillText(text, 0, ascent);

		const image = ctx.getImageData(0, 0, w, h);
		const data = image.data;
		for (let i = 3; i < data.length; i += 4) data[i] = data[i] > 108 ? 255 : 0;
		ctx.putImageData(image, 0, 0);
	}

	// The heading is the element's own text until this runs, so a failure here
	// leaves a perfectly good unpixelated numeral rather than an empty box.
	node.textContent = '';
	node.appendChild(canvas);
	draw();

	// Font size is set in CSS and the face loads asynchronously; both change what
	// there is to draw.
	const observer = new ResizeObserver(draw);
	observer.observe(node);
	if (document.fonts?.ready) document.fonts.ready.then(draw);

	return {
		destroy() {
			observer.disconnect();
		}
	};
}
