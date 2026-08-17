/**
 * The displacement map behind the screen's curve.
 *
 * `feDisplacementMap` bends its source by reading a *second* image: at each
 * pixel it takes two channels of that image as an (x, y) offset and samples the
 * source from there instead. So the curve is entirely a question of what is in
 * the map, and the map is a picture of a barrel distortion.
 *
 * The encoding is the part that matters, and it is not the obvious one.
 *
 * A displacement of `d` is stored as the channel value `128 + d * 127`, and the
 * filter reads it back as `scale * (channel / 255 - 0.5)`. Store the
 * displacement at its natural size and a gentle curve — the only kind anyone
 * wants to read a journal through — occupies about 50 of the 255 available
 * levels. Eight-bit quantisation then lands every pixel of a long straight line
 * on one of ~50 discrete offsets, and the line comes out as a visible staircase
 * of disconnected segments. That is not the curve being wrong; it is the map
 * running out of numbers.
 *
 * So the map is **normalised**: the displacement field is divided by its own
 * maximum, which puts the corners at the full ±127 and uses all 255 levels
 * whatever the curve strength. The magnitude is then carried by
 * `feDisplacementMap`'s `scale` instead, which is a float and does not quantise.
 * Same curve, ~5x the precision, and the staircase is gone.
 *
 * What this cannot fix: the primitive point-samples its source, so 1px
 * hairlines still fray slightly where the stretch is largest, out at the
 * corners. It halves on a 2x display — the filter runs in device pixels — and
 * it is the reason `CORNER_PX` is small.
 */

/**
 * How far the very corners of the screen move, in CSS pixels.
 *
 * This is the whole tuning knob, and it is deliberately in pixels rather than
 * in some abstract curvature number, because it *is* the cost: layout does not
 * move when the picture does, so a control near the corner is up to this far
 * from where it looks. At 20px the middle two-thirds of the screen are visually
 * untouched — the falloff is quadratic in the radius — and nothing is far
 * enough from its hit area to miss.
 */
export const CORNER_PX = 12;

/**
 * Map resolution. It is stretched over the viewport, so this is about how
 * smoothly the field interpolates rather than about detail; 512 is past the
 * point where raising it changes anything visible, and it is generated once.
 */
const MAP_SIZE = 512;

/**
 * `scale` for a given corner displacement.
 *
 * The filter reads `scale * (channel / 255 - 0.5)`, and a normalised map puts
 * the corner channel at 255, so the corner offset is `scale * 0.498`. Invert
 * that to ask for a displacement in pixels and get the scale back.
 */
export function barrelScale(cornerPx: number = CORNER_PX): number {
	// channel 255 → (255/255 - 0.5) = 0.5, so the corner offset is scale/2.
	return cornerPx * 2;
}

/**
 * The map itself, as a data URL.
 *
 * Barrel distortion is `p * (1 + k * r²)` — the offset grows with the square of
 * the distance from the centre, which is why the middle stays put and only the
 * corners move. `k` cancels out under normalisation, so it is not a parameter
 * here: every barrel of this family has the same *shape*, and only `scale`
 * decides how far it goes.
 *
 * Browser-only: it draws on a canvas. Callers guard with `browser`.
 */
export function barrelMap(size: number = MAP_SIZE): string {
	const canvas = document.createElement('canvas');
	canvas.width = size;
	canvas.height = size;

	const ctx = canvas.getContext('2d');
	if (!ctx) return '';

	const image = ctx.createImageData(size, size);
	const data = image.data;

	// The maximum of |n * r²| over the square, reached at a corner where each
	// axis is 1 and r² is 2. Dividing by it is what fills the channel range.
	const peak = 2;

	for (let y = 0; y < size; y++) {
		for (let x = 0; x < size; x++) {
			const nx = (x / (size - 1)) * 2 - 1;
			const ny = (y / (size - 1)) * 2 - 1;
			const r2 = nx * nx + ny * ny;
			const i = (y * size + x) * 4;

			data[i] = clampByte(128 + ((nx * r2) / peak) * 127);
			data[i + 1] = clampByte(128 + ((ny * r2) / peak) * 127);
			// Blue is unread by the filter; alpha must be opaque or the
			// displacement is scaled down by it.
			data[i + 2] = 128;
			data[i + 3] = 255;
		}
	}

	ctx.putImageData(image, 0, 0);
	return canvas.toDataURL();
}

function clampByte(value: number): number {
	return Math.max(0, Math.min(255, Math.round(value)));
}
