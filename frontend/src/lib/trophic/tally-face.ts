/**
 * The sticker's shape and its printed face — everything about it that is 2D.
 *
 * Kept apart from `tally-scene.ts` because that one imports three.js at module
 * scope and this one must not: the component loads the scene lazily and needs
 * the shape and the face on hand before, and whether or not, that arrives. A
 * machine with no WebGL draws the same face flat out of here.
 *
 * So this is the single source of the geometry. The mesh's outline and the
 * fallback's clip are the same list of points, and the ring of text and the
 * figures are painted once by `paintFace`, whether they are about to become a
 * texture or to be shown as they are.
 */

/** The die cut: 22 spikes, notched to 85.5% of the radius. Both numbers were
 *  looked at rather than reasoned to — fewer and deeper reads as a star, which
 *  is a rating; more and shallower reads as a gear. This is the shape a sticker
 *  off a roll has. */
export const SPIKES = 22;
export const NOTCH = 0.855;

/** The face is drawn at four times the size it is seen at, so the ring of text
 *  stays crisp on a 2× display and while the sticker is turned away. */
export const TEXTURE = 512;

/** The legend, and the ring it stands on. The radius is a fraction of the
 *  sticker's own, chosen to clear the notches: at 0.72 the text sits inside the
 *  deepest cut with room to spare, which is what leaves the middle of the
 *  sticker empty for the number.
 *
 *  It is split across the top and the bottom of the ring rather than run once
 *  around it. A single circuit puts everything past three o'clock upside down —
 *  which is what a ring of type does, and is why a coin has never been set that
 *  way: the bottom half is struck the other way up so both halves read left to
 *  right. Two arcs and a dot at each side is that arrangement. */
export const RING_RADIUS = 0.72;
export const RING_TOP = 'all time';
export const RING_BOTTOM = 'todos!';
/** Radians of ring per glyph. Wider than the type needs, because tracking is
 *  what makes a legend look struck rather than typed. */
export const RING_STEP = 0.26;

/**
 * How much wider than the sticker its canvas is, as a multiple of the
 * sticker's radius.
 *
 * It lives here, in the module both sides import, because two things are
 * struck from it and they have to agree exactly: the component sizes the
 * canvas element by it, and the scene pulls the camera back by it. Written
 * twice, a change to one silently resizes the sticker.
 *
 * What the margin is *for* is the glow. The sticker turns and advances, so it
 * needs a little room; the halo behind it needs a great deal more, because a
 * glow that reaches the edge of the canvas is sliced off in a straight line
 * down the side. See `tally-scene.ts`, where the halo's radius is struck from
 * this and the frustum rather than chosen.
 */
export const FRAME = 1.6;

export interface Figures {
	done: number;
	made: number;
}

/** The outline, as points on a unit circle with a spike at twelve o'clock. */
export function burstPoints(): [number, number][] {
	const points: [number, number][] = [];
	for (let i = 0; i < SPIKES * 2; i++) {
		const radius = i % 2 === 0 ? 1 : NOTCH;
		const angle = (i * Math.PI) / SPIKES - Math.PI / 2;
		points.push([radius * Math.cos(angle), radius * Math.sin(angle)]);
	}
	return points;
}

/** A colour off the document's own ramp. Read rather than written here so the
 *  badge cannot drift off the one hue `app.css` defines, and follows it if it
 *  moves. */
export function css(name: string, fallback: string): string {
	if (typeof document === 'undefined') return fallback;
	const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
	return value || fallback;
}

function mono(weight: number, size: number): string {
	return `${weight} ${size}px "JetBrains Mono Variable", ui-monospace, monospace`;
}

/**
 * Set one line of text along an arc, one glyph at a time, centred on `centre`
 * measured clockwise from twelve o'clock.
 *
 * Every glyph gets an equal slice of the arc rather than its own width. In a
 * monospaced face those are nearly the same thing, and the difference — the
 * spaces taking a full slot — is what opens the legend out into the tracking a
 * stamped seal has.
 *
 * `flip` turns each glyph over and runs them the other way round the circle,
 * which is what the bottom arc needs: struck the same way as the top it would
 * be legible only upside down.
 */
function arc(
	ctx: CanvasRenderingContext2D,
	text: string,
	radius: number,
	size: number,
	centre: number,
	flip = false
): void {
	const glyphs = [...text.toUpperCase()];
	const step = flip ? -RING_STEP : RING_STEP;
	const start = centre - ((glyphs.length - 1) / 2) * step;
	ctx.save();
	ctx.translate(TEXTURE / 2, TEXTURE / 2);
	ctx.font = mono(700, size);
	ctx.textAlign = 'center';
	ctx.textBaseline = 'middle';
	glyphs.forEach((glyph, i) => {
		ctx.save();
		// Rotate first, then step outward along the local -Y: that lands the
		// glyph at its own angle clockwise from the top, standing upright off
		// the ring.
		ctx.rotate(start + i * step);
		ctx.translate(0, -radius);
		if (flip) ctx.rotate(Math.PI);
		ctx.fillText(glyph, 0, 0);
		ctx.restore();
	});
	ctx.restore();
}

/** The two beads that close the ring at three and nine o'clock. Without them
 *  the legend reads as two unrelated lines that happen to be curved; with them
 *  it is one band around the sticker with the figure inside it. */
function beads(ctx: CanvasRenderingContext2D, radius: number): void {
	ctx.save();
	ctx.translate(TEXTURE / 2, TEXTURE / 2);
	for (const side of [-1, 1]) {
		ctx.beginPath();
		ctx.arc(side * radius, 0, 6, 0, Math.PI * 2);
		ctx.fill();
	}
	ctx.restore();
}

/**
 * The whole printed face at texture resolution: the stock it is stamped on, the
 * sheen across it, the ring of text and the figures.
 *
 * The context is expected to be `TEXTURE` square. The caller scales.
 */
export function paintFace(ctx: CanvasRenderingContext2D, figures: Figures): void {
	const mid = TEXTURE / 2;
	const ink = css('--color-accent', '#ffffff');
	const dim = css('--color-neutral-700', '#3cbe77');
	const faint = css('--color-neutral-500', '#2d8f5a');

	ctx.clearRect(0, 0, TEXTURE, TEXTURE);

	// The stock, with the tube's sheen falling across it from the top left —
	// the same direction the key light on the mesh comes from, so the painted
	// highlight and the lit rim agree about where the light is.
	ctx.fillStyle = css('--color-surface', '#0c1519');
	ctx.fillRect(0, 0, TEXTURE, TEXTURE);
	const sheen = ctx.createLinearGradient(0, 0, TEXTURE, TEXTURE);
	sheen.addColorStop(0, 'rgba(255, 255, 255, 0.18)');
	sheen.addColorStop(0.55, 'rgba(255, 255, 255, 0.05)');
	sheen.addColorStop(1, 'rgba(255, 255, 255, 0.02)');
	ctx.fillStyle = sheen;
	ctx.fillRect(0, 0, TEXTURE, TEXTURE);

	const ring = mid * RING_RADIUS;
	ctx.fillStyle = dim;
	arc(ctx, RING_TOP, ring, 44, 0);
	arc(ctx, RING_BOTTOM, ring, 44, Math.PI, true);
	beads(ctx, ring);

	// The figures, dead centre and as large as the ring leaves room for. Fitted
	// rather than fixed: `2/5` and `1,204/1,318` are the same badge, and a
	// number that gains a digit must not run into the beads at its sides.
	const done = figures.done.toLocaleString();
	const made = figures.made.toLocaleString();
	const room = 2 * (ring - 34);
	let big = 132;
	let small = 74;
	const measure = () => {
		ctx.font = mono(800, big);
		const a = ctx.measureText(done).width;
		ctx.font = mono(600, small);
		return a + ctx.measureText(`/${made}`).width;
	};
	const total = measure();
	if (total > room) {
		const scale = room / total;
		big = Math.floor(big * scale);
		small = Math.floor(small * scale);
	}

	ctx.textAlign = 'left';
	ctx.textBaseline = 'alphabetic';
	const width = measure();
	const left = mid - width / 2;
	// Optically centred on the digits rather than on the line box: the legend
	// sits low on the ring, and a figure centred on its own baseline would look
	// as though it had slipped upward.
	const baseline = mid + big * 0.36;

	ctx.font = mono(800, big);
	ctx.fillStyle = ink;
	ctx.fillText(done, left, baseline);
	const afterDone = left + ctx.measureText(done).width;
	ctx.font = mono(600, small);
	ctx.fillStyle = faint;
	ctx.fillText('/', afterDone, baseline);
	ctx.fillStyle = dim;
	ctx.fillText(made, afterDone + ctx.measureText('/').width, baseline);
}

/**
 * The whole sticker, flat, for a machine with no WebGL.
 *
 * Everything the mesh gets from being a solid is gone — there is no thickness,
 * no lamp on the rim and nothing to turn toward the pointer — and that is the
 * right amount to lose. It is the same die cut and the same printed face, drawn
 * once and never again, and it is a badge rather than a hole where one was.
 */
export function paintFlat(ctx: CanvasRenderingContext2D, figures: Figures, size: number): void {
	const scale = size / TEXTURE;
	const mid = TEXTURE / 2;
	ctx.save();
	ctx.clearRect(0, 0, size, size);
	ctx.scale(scale, scale);

	ctx.beginPath();
	burstPoints().forEach(([x, y], i) => {
		const px = mid + x * mid;
		const py = mid + y * mid;
		if (i === 0) ctx.moveTo(px, py);
		else ctx.lineTo(px, py);
	});
	ctx.closePath();
	ctx.save();
	ctx.clip();
	paintFace(ctx, figures);
	ctx.restore();

	// The cut edge, as a hairline: with no rim to light there is nothing else
	// to separate the sticker from the ground behind it.
	ctx.strokeStyle = css('--color-accent', '#ffffff');
	ctx.globalAlpha = 0.55;
	ctx.lineWidth = 5;
	ctx.stroke();
	ctx.restore();
}
