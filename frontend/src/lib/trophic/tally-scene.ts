/**
 * The tally sticker as an actual object: the die cut extruded into a solid,
 * bevelled, lit, and turned in front of a perspective camera.
 *
 * ## Why this stopped being CSS
 *
 * It was a stack of seven copies of the same silhouette pushed back in
 * `translateZ`, which is the only way CSS can suggest thickness. That reads as
 * an object at a glance and falls apart when you look at it: the side is seven
 * flat plates with steps between them, it takes light from nowhere, and the
 * rolled edge that makes a real seal catch the light cannot exist at all. This
 * is one mesh with a bevelled rim, two materials and two lamps — the edge is
 * bright because a light is on it, not because a plate was set to a brighter
 * green.
 *
 * ## What it costs, which is the thing to watch
 *
 * **It renders on demand and idles at zero.** No loop runs behind this screen.
 * A frame is drawn while the tilt is easing toward a new pointer position,
 * while a pulse plays, and when the figures change: `wake()` starts the loop
 * and `draw()` stops it the moment nothing is moving. The idle drift is a CSS
 * transform on the wrapper and costs no GL at all.
 *
 * That matters more here than it would anywhere else. This sits on the capture
 * screen, where every keystroke is a repaint, and CLAUDE.md records what the
 * last full-time effect on this screen cost: 23ms of every frame. A still
 * WebGL canvas costs nothing per frame — it is composited like an image.
 *
 * ## The face is painted, not modelled
 *
 * The figures and the ring of text are a 2D canvas used as the mesh's colour
 * and emissive map — see `tally-face.ts`, which also draws the flat fallback.
 * Text as geometry would want a font loader, a typeface shipped as JSON and a
 * mesh rebuilt every time the count ticks; a canvas redraw is two lines, and
 * the type is the same JetBrains Mono the rest of the app is set in.
 */
import * as THREE from 'three';

import { FRAME, TEXTURE, burstPoints, css, paintFace, type Figures } from './tally-face';

export interface Tally {
	/** Point the face somewhere, in degrees. A standing request, not a command:
	 *  it is a spring the sticker settles onto once it has stopped being
	 *  played with. */
	aim(turn: number, pitch: number): void;
	/** Redraw the face for a new pair of numbers. */
	setFigures(figures: Figures): void;
	/** A promise kept comes forward; one made takes the weight backwards. */
	pulse(kind: 'kept' | 'made'): void;
	/** Take hold of it. The spring lets go while this is true, so it turns
	 *  exactly as far as it is pushed and no further. */
	grab(): void;
	/** Turn it by a pointer movement, in pixels. */
	drag(dx: number, dy: number): void;
	/** Let go. Whatever speed it was moving at, it keeps. */
	release(): void;
	/** A tap: a small shove, in a direction it did not choose. */
	nudge(): void;
	dispose(): void;
}

/** How thick the sticker is, as a fraction of its radius, and how much of that
 *  is rolled off into the bevel. The bevel is the whole reason the rim reads as
 *  something stamped: a square edge takes one flat band of light, a rolled one
 *  takes a gradient and a highlight along the crest. */
const DEPTH = 0.3;
const BEVEL = 0.06;

/** How far behind the sticker the halo sits, and the most it may swell when the
 *  thing is being worked hard. */
const HALO_Z = 0.55;
const HALO_SWELL = 0.16;

/**
 * How it behaves when it is being played with.
 *
 * It is a physical toy and nothing else — there is no gesture here that does
 * anything to the app. Pick it up, turn it over, throw it and watch it spin
 * down. All four numbers were tuned by throwing it rather than derived:
 *
 *   `TURN_PER_PX`  a hand's width of drag is a bit more than half a turn
 *   `FRICTION`     per frame; a hard flick runs about two seconds
 *   `SPRING`       what pulls it back to the resting angle, weak enough that it
 *                  loses a spin to friction first and settles second
 *   `TOP_SPEED`    a cap, so a flick off the edge of a trackpad cannot make it
 *                  a strobe
 */
const TURN_PER_PX = 0.009;
const FRICTION = 0.94;
const SPRING = 0.0055;
const TOP_SPEED = 0.55;

/** How much of the rest angle the pitch keeps hold of. Turning is a spin and
 *  should run free; tumbling forwards is a wobble, and a badge that ends up
 *  reading upside down is a badge somebody has to fix by hand. */
const PITCH_SPRING = 3;

const rad = (deg: number) => (deg * Math.PI) / 180;

/** The same angle written between -π and π, so the spring pulls toward the
 *  nearest way round rather than unwinding every full turn it was given. This
 *  is what lets a flick spin four times and still settle where it started. */
function shortest(angle: number): number {
	const wrapped = ((angle + Math.PI) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2);
	return wrapped - Math.PI;
}

/** The halo behind it: a soft disc of phosphor, brightest at the middle. Drawn
 *  rather than blurred, because a blur is a filter and a filter on this screen
 *  is a rasterise on every frame — see CLAUDE.md. */
function glowTexture(): THREE.CanvasTexture {
	const size = 256;
	const canvas = document.createElement('canvas');
	canvas.width = size;
	canvas.height = size;
	const g = canvas.getContext('2d')!;
	const grad = g.createRadialGradient(size / 2, size / 2, size * 0.16, size / 2, size / 2, size / 2);
	const accent = css('--color-accent', '#ffffff');
	grad.addColorStop(0, accent);
	grad.addColorStop(0.42, 'rgba(255, 255, 255, 0.28)');
	grad.addColorStop(1, 'rgba(255, 255, 255, 0)');
	g.fillStyle = grad;
	g.fillRect(0, 0, size, size);
	const texture = new THREE.CanvasTexture(canvas);
	texture.colorSpace = THREE.SRGBColorSpace;
	return texture;
}

/** The outline as three.js wants it. Straight lines between the same points
 *  `tally-face` clips the flat one to — one geometry, two renderers. */
function burst(): THREE.Shape {
	const shape = new THREE.Shape();
	burstPoints().forEach(([x, y], i) => {
		// Canvas y runs down and three's runs up, so the shape is flipped here
		// rather than in the shared list. The cut is symmetric about the
		// vertical, so this only decides which way round the spikes are indexed.
		if (i === 0) shape.moveTo(x, -y);
		else shape.lineTo(x, -y);
	});
	shape.closePath();
	return shape;
}

/**
 * Put the sticker in the given canvas and hand back the three things the
 * component drives it with. Throws when the machine has no WebGL, which is the
 * caller's cue to draw the flat one instead.
 */
export function mount(canvas: HTMLCanvasElement, initial: Figures): Tally {
	const renderer = new THREE.WebGLRenderer({
		canvas,
		alpha: true,
		antialias: true,
		// Because this renders on demand. The drawing buffer is cleared after it
		// is composited, so a canvas that has stopped drawing has nothing to give
		// the next composite that does not come from a frame — which is most of
		// this badge's life, and every screenshot of it.
		preserveDrawingBuffer: true
	});
	renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
	renderer.setSize(canvas.clientWidth, canvas.clientHeight, false);

	const scene = new THREE.Scene();
	// A wide lens, close in. Something with twenty-two points is very nearly a
	// circle, so turning it barely changes its outline — the near spikes coming
	// up bigger than the far ones is most of what says this is a solid at all,
	// and that is perspective rather than rotation. A long lens flattens it back
	// into a sticker printed on the screen.
	const FOV = 42;
	const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 20);
	// Far enough back that the sticker's own diameter of 2 fills all but the
	// margin of the frame. Struck this way round, the visible half-width at the
	// sticker's own plane comes out at exactly `FRAME`, which is what the halo
	// below is measured against.
	camera.position.z = FRAME / Math.tan(rad(FOV) / 2);

	let figures = initial;
	const face = document.createElement('canvas');
	face.width = TEXTURE;
	face.height = TEXTURE;
	const ctx = face.getContext('2d');
	if (!ctx) throw new Error('no 2d context for the sticker face');
	paintFace(ctx, figures);

	const texture = new THREE.CanvasTexture(face);
	texture.colorSpace = THREE.SRGBColorSpace;
	texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
	// The cap UVs come back in the shape's own coordinates, which run -1..1.
	// Halving the repeat and offsetting by half maps that onto the 0..1 the
	// texture wants, so the painted face lands exactly on the cut's bounds.
	texture.repeat.set(0.5, 0.5);
	texture.offset.set(0.5, 0.5);

	const geometry = new THREE.ExtrudeGeometry(burst(), {
		depth: DEPTH,
		bevelEnabled: true,
		bevelThickness: BEVEL,
		bevelSize: BEVEL,
		bevelSegments: 3,
		// The outline is already a polygon; asking for curve segments on it
		// would only multiply vertices along lines that are straight.
		curveSegments: 1
	});
	// Extrusion runs backwards from the front face, so the solid is pushed half
	// its depth forward to turn about its own middle rather than about its back.
	geometry.translate(0, 0, -DEPTH / 2);

	// `Physical` rather than `Standard` for one property: `clearcoat`. It is a
	// second, thin, glossy layer over the print — laminate over a label — and it
	// carries its own specular highlight independent of how rough the stock
	// under it is. That highlight is the gloss: a hard little streak that slides
	// across the face as the sticker turns, and the single strongest cue that
	// there is a real surface here catching a real light.
	const capMaterial = new THREE.MeshPhysicalMaterial({
		map: texture,
		emissiveMap: texture,
		emissive: new THREE.Color(0xffffff),
		// Enough that the print looks lit from within, like everything else on
		// this ground, and not so much that the lamps stop showing on the face.
		emissiveIntensity: 0.7,
		roughness: 0.52,
		metalness: 0.12,
		clearcoat: 1,
		clearcoatRoughness: 0.14
	});
	// The rim: darker than the face and far shinier. It is the cut edge of the
	// stock, and everything it shows comes from the lamps rather than the print.
	const rimMaterial = new THREE.MeshStandardMaterial({
		color: new THREE.Color(css('--color-neutral-400', '#1f583f')),
		emissive: new THREE.Color(css('--color-accent', '#ffffff')),
		emissiveIntensity: 0.16,
		roughness: 0.26,
		metalness: 0.6
	});

	const mesh = new THREE.Mesh(geometry, [capMaterial, rimMaterial]);
	scene.add(mesh);

	// The halo, on its own plate behind the sticker rather than parented to it:
	// it is light in the air around the thing, so it must not turn when the
	// thing turns. Depth is written by the sticker and not by this, so what
	// shows through the gaps between the spikes is the glow behind them.
	//
	// **Its radius is measured, not chosen.** The gradient painted on it fades
	// to nothing exactly at its own rim, so a plate that sits wholly inside the
	// frame has no edge anyone can see — and one that overruns the frame is cut
	// off in a straight line down the side of the canvas the moment the glow is
	// bright enough to show it. That line is the one artefact that gives away
	// that this is a picture in a box rather than an object on the screen, and
	// it appears exactly when the badge is at its most alive.
	//
	// So: take the visible half-width at the plate's own plane, which is wider
	// than the sticker's because the plate is further from the camera, keep 3%
	// back, and divide by the most it is ever allowed to swell to. That is the
	// largest glow that can never touch the edge, and it stays right if the
	// frame, the lens or the swell is ever retuned.
	const room = (FRAME * (camera.position.z + HALO_Z)) / camera.position.z;
	const halo = new THREE.Mesh(
		new THREE.CircleGeometry((room * 0.97) / (1 + HALO_SWELL), 48),
		new THREE.MeshBasicMaterial({
			map: glowTexture(),
			transparent: true,
			opacity: 0.2,
			depthWrite: false
		})
	);
	halo.position.z = -HALO_Z;
	scene.add(halo);

	// Two lamps and an ambient, and no more. The key sits up and to the left,
	// where the sheen painted into the face already says the light is; the fill
	// is behind and to the right, dim, and exists only so the spikes on the far
	// side are cut out of the ground rather than lost in it. Both are phosphor:
	// a white lamp would put a second hue on the one screen with a rule against
	// it, and the rule is about what reaches the glass, not about CSS.
	const key = new THREE.DirectionalLight(new THREE.Color(0xa9ffd2), 2.6);
	key.position.set(-2.2, 2.6, 3.2);
	scene.add(key);
	const fill = new THREE.DirectionalLight(new THREE.Color(css('--color-accent', '#ffffff')), 0.9);
	fill.position.set(2.4, -1.4, -1.2);
	scene.add(fill);
	scene.add(new THREE.AmbientLight(new THREE.Color(css('--color-accent', '#ffffff')), 0.3));

	let aimTurn = 0;
	let aimPitch = 0;
	/** Radians per frame, on each axis. This is the whole toy. */
	let spinY = 0;
	let spinX = 0;
	let held = false;
	/** Where a pulse is pushing it along the axis into the screen, and where it
	 *  actually is. */
	let pushTo = 0;
	let push = 0;
	/**
	 * How hard it is being worked, 0 to 1, smoothed.
	 *
	 * Everything that answers the interaction answers *this* rather than
	 * answering the pointer: the print burns brighter, the cut edge picks up,
	 * and the halo swells and spreads. One number driving three things is what
	 * keeps them agreeing with each other — a glow that brightened on a
	 * different schedule from the rim would read as two effects on one object.
	 *
	 * It rises fast and falls slowly, so a flick lights it at once and the light
	 * outlives the spin by a moment rather than snapping off with it.
	 */
	let heat = 0;
	let frame = 0;
	let living = true;

	function wake() {
		if (!living || frame) return;
		frame = requestAnimationFrame(draw);
	}

	function draw() {
		frame = 0;

		if (!held) {
			// The spring, and the reason the angle is wrapped first: a flick that
			// spun it three times is three times around from where it wants to
			// be, and a spring reading that literally would haul it back like a
			// rewinding tape. Wrapped, it simply settles on the nearest way round
			// — so a spin looks like a spin and ends where it began.
			spinY += shortest(rad(aimTurn) - mesh.rotation.y) * SPRING;
			spinX += shortest(rad(-aimPitch) - mesh.rotation.x) * SPRING * PITCH_SPRING;
			spinY *= FRICTION;
			spinX *= FRICTION;
			mesh.rotation.y += spinY;
			mesh.rotation.x += spinX;
		}

		// Out fast, home slowly — the same asymmetry the capture bar's typing
		// glow uses, and for the same reason.
		push += (pushTo - push) * (pushTo === 0 ? 0.07 : 0.22);
		mesh.position.z = push;

		const worked = Math.min(1, (Math.abs(spinY) + Math.abs(spinX)) / 0.22);
		heat += (worked - heat) * (worked > heat ? 0.3 : 0.045);
		capMaterial.emissiveIntensity = 0.7 + heat * 0.5;
		rimMaterial.emissiveIntensity = 0.16 + heat * 0.42;
		(halo.material as THREE.MeshBasicMaterial).opacity = 0.2 + heat * 0.55;
		halo.scale.setScalar(1 + heat * HALO_SWELL);

		renderer.render(scene, camera);

		// A pulse is a there-and-back: once it has arrived, aim it home.
		if (pushTo !== 0 && Math.abs(pushTo - push) < 0.02) pushTo = 0;

		const settled =
			!held &&
			Math.abs(spinY) < 0.0002 &&
			Math.abs(spinX) < 0.0002 &&
			Math.abs(shortest(rad(aimTurn) - mesh.rotation.y)) < 0.0008 &&
			Math.abs(pushTo - push) < 0.0015 &&
			heat < 0.004;
		if (settled) {
			// Land it exactly, so a sticker left alone for an hour is not
			// drifting a thousandth of a radian a minute.
			mesh.rotation.y = rad(aimTurn);
			mesh.rotation.x = rad(-aimPitch);
			heat = 0;
			capMaterial.emissiveIntensity = 0.7;
			rimMaterial.emissiveIntensity = 0.16;
			(halo.material as THREE.MeshBasicMaterial).opacity = 0.2;
			halo.scale.setScalar(1);
			renderer.render(scene, camera);
			return;
		}
		wake();
	}

	// Drawn straight away rather than on the next frame: the badge should be on
	// screen the moment the canvas is.
	draw();
	// Webfonts land after the first paint and the legend set in a fallback face
	// has different metrics, so the face is painted again once they are in.
	document.fonts?.ready.then(() => {
		if (!living) return;
		paintFace(ctx, figures);
		texture.needsUpdate = true;
		wake();
	});

	return {
		aim(turn, pitch) {
			aimTurn = turn;
			aimPitch = pitch;
			wake();
		},
		setFigures(next) {
			figures = next;
			paintFace(ctx, figures);
			texture.needsUpdate = true;
			wake();
		},
		pulse(kind) {
			// Toward the reader for a promise kept, away for one made, and half
			// the travel for the second — writing a todo down is a debt, and the
			// badge should not congratulate you for it.
			pushTo = kind === 'kept' ? 0.62 : -0.3;
			// A kept promise also sets it turning. This is the one place the
			// toy and the tally meet: the thing you can spin for fun spins on
			// its own when the number it carries goes up.
			if (kind === 'kept') spinY += 0.16;
			wake();
		},
		grab() {
			held = true;
			spinY = 0;
			spinX = 0;
			wake();
		},
		drag(dx, dy) {
			mesh.rotation.y += dx * TURN_PER_PX;
			mesh.rotation.x += dy * TURN_PER_PX;
			// The speed it will be let go at, smoothed across a few events: a
			// pointer reports faster than this draws, and the last event on its
			// own is as likely to be a twitch as a throw.
			spinY = spinY * 0.55 + dx * TURN_PER_PX * 0.45;
			spinX = spinX * 0.55 + dy * TURN_PER_PX * 0.45;
			wake();
		},
		release() {
			held = false;
			spinY = Math.max(-TOP_SPEED, Math.min(TOP_SPEED, spinY));
			spinX = Math.max(-TOP_SPEED, Math.min(TOP_SPEED, spinX));
			wake();
		},
		nudge() {
			// A tap rather than a drag. It gets a shove of a size it did not
			// ask for and a direction it did not choose, because a toy that
			// answers a poke with the same motion every time stops being one.
			spinY += (Math.random() < 0.5 ? -1 : 1) * (0.09 + Math.random() * 0.07);
			spinX += (Math.random() - 0.5) * 0.05;
			push = 0.1;
			wake();
		},
		dispose() {
			living = false;
			if (frame) cancelAnimationFrame(frame);
			geometry.dispose();
			capMaterial.dispose();
			rimMaterial.dispose();
			texture.dispose();
			halo.geometry.dispose();
			const haze = halo.material as THREE.MeshBasicMaterial;
			haze.map?.dispose();
			haze.dispose();
			renderer.dispose();
		}
	};
}
