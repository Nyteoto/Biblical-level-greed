<script lang="ts">
	/**
	 * The log's navigation: a vertical, zoomable date ruler.
	 * Ported from `components/TimelineNav.tsx` + `hooks/useTimelineInteraction.ts`.
	 *
	 * The gesture vocabulary is the whole point and is kept exactly:
	 *   wheel            scroll through time, eased toward a target over rAF
	 *   alt/meta + wheel zoom about the cursor (pixels-per-day, 0.03 → 40)
	 *   ctrl + wheel     cycle day → week → month
	 *   drag             1:1 scroll, no easing
	 *   click            select the date under the pointer
	 *   pinch            zoom about the midpoint
	 *   double-tap       cycle the span
	 *
	 * Selection is not "the thing you clicked" — it is whatever sits at the
	 * fixed centre arrow, updated continuously as you scroll. The ruler moves
	 * under a stationary reading head, which is why the arrow is drawn outside
	 * the canvas and never moves.
	 *
	 * ppd/scroll/span persist to localStorage per key, so the log opens where
	 * you left it. That is view state, not user data, and belongs there.
	 */
	import { drawTimeline, type ViewSpan } from './timeline-draw';

	let {
		dates = {},
		selected = null,
		viewSpan = $bindable('day' as ViewSpan),
		dense = false,
		storageKey = 'global',
		onselect
	}: {
		dates: Record<string, number>;
		selected: string | null;
		viewSpan: ViewSpan;
		dense?: boolean;
		storageKey?: string;
		onselect: (date: string) => void;
	} = $props();

	const W = 48;
	const MIN_PPD = 0.03;
	const MAX_PPD = 40;
	const SPAN_ORDER: ViewSpan[] = ['day', 'week', 'month'];
	const STORAGE_PREFIX = 'trophic-timeline-';

	let box = $state<HTMLDivElement | null>(null);
	let canvas = $state<HTMLCanvasElement | null>(null);
	let h = $state(0);

	// Mutable view state. Deliberately not $state: these change on every frame
	// of a drag and drive an imperative canvas, so reactivity would only add
	// re-render churn to something that redraws itself.
	let ppd = 2;
	let scroll = 0;
	let targetScroll = 0;
	let smoothAnim = 0;
	let labelAlpha = 0;
	let labelTarget = 0;
	let labelAnim = 0;
	let drag = { active: false, startY: 0, startScroll: 0, moved: false };
	let hovering = false;
	let spanCooldown = false;
	let initialised = false;

	/**
	 * Midnight of *your* today, as a UTC instant.
	 *
	 * The local calendar date, deliberately — this read `getUTCFullYear()` and
	 * friends, which is a different day for most of the world for part of every
	 * day. East of Greenwich the ruler was a day behind from local midnight
	 * until the offset caught up: capture something at 00:01 and the backend
	 * files it under your day while the ruler is still drawing yesterday, so
	 * the entry you just wrote is one screen above the one you are looking at.
	 *
	 * The anchor stays a UTC *instant* because everything downstream reads it
	 * with `getUTC*` — see timeline-draw.ts, whose 22 corpus cases pin that.
	 * Only which calendar day it points at changes.
	 */
	const todayMs = (() => {
		const n = new Date();
		return Date.UTC(n.getFullYear(), n.getMonth(), n.getDate());
	})();

	/** How far back the ruler can go: a year, or past the oldest entry. */
	const maxDA = $derived.by(() => {
		const keys = Object.keys(dates);
		if (keys.length === 0) return 365;
		const oldest = keys.reduce((a, b) => (a < b ? a : b));
		const oldestDA = Math.round((todayMs - new Date(oldest + 'T00:00:00Z').getTime()) / 86400000);
		return Math.max(365, oldestDA + 30);
	});

	function clampScroll(s: number): number {
		const half = h / (2 * ppd);
		return Math.max(-half, Math.min(maxDA - half, s));
	}

	function daToKey(n: number): string {
		return new Date(todayMs - n * 86400000).toISOString().slice(0, 10);
	}

	function draw() {
		if (!canvas || h === 0) return;
		const dpr = window.devicePixelRatio || 1;
		canvas.width = W * dpr;
		canvas.height = h * dpr;
		const ctx = canvas.getContext('2d');
		if (!ctx) return;
		ctx.scale(dpr, dpr);
		drawTimeline({
			ctx,
			W,
			h,
			ppd,
			scroll,
			labelAlpha,
			dates,
			selected,
			viewSpan,
			todayMs,
			dense
		});
	}

	// Redraw when anything reactive that the canvas shows changes.
	$effect(() => {
		void dates;
		void selected;
		void viewSpan;
		void h;
		void dense;
		draw();
	});

	let lastEmitted = '';
	/** Select whatever the centre arrow is pointing at. */
	function selectCentre() {
		const daysAgo = scroll + h / (2 * ppd);
		const key = daToKey(Math.max(0, Math.round(daysAgo)));
		// The centre moves every frame but only crosses a day boundary now and
		// then; emitting only on change keeps the log from refetching per frame.
		if (key !== lastEmitted) {
			lastEmitted = key;
			onselect(key);
		}
	}

	function persist() {
		try {
			localStorage.setItem(
				STORAGE_PREFIX + storageKey,
				JSON.stringify({ ppd, scroll, viewSpan })
			);
		} catch {
			/* private mode, quota, whatever — view state is not worth an error */
		}
	}

	function startLabelAnim(target: number) {
		labelTarget = target;
		if (labelAnim) return;
		const tick = () => {
			const diff = labelTarget - labelAlpha;
			if (Math.abs(diff) < 0.01) {
				labelAlpha = labelTarget;
				draw();
				labelAnim = 0;
				return;
			}
			// Fades in four times faster than it fades out.
			labelAlpha += diff * (labelTarget > labelAlpha ? 0.25 : 0.08);
			draw();
			labelAnim = requestAnimationFrame(tick);
		};
		labelAnim = requestAnimationFrame(tick);
	}

	function stopSmooth() {
		if (smoothAnim) {
			cancelAnimationFrame(smoothAnim);
			smoothAnim = 0;
		}
	}

	function startSmooth() {
		if (smoothAnim) return;
		const tick = () => {
			const diff = targetScroll - scroll;
			if (Math.abs(diff) < 0.01) {
				scroll = targetScroll;
				smoothAnim = 0;
				draw();
				selectCentre();
				persist();
				return;
			}
			scroll = clampScroll(scroll + diff * 0.2);
			draw();
			selectCentre();
			smoothAnim = requestAnimationFrame(tick);
		};
		smoothAnim = requestAnimationFrame(tick);
	}

	// Measure the box; everything downstream is in its height.
	$effect(() => {
		if (!box) return;
		const ro = new ResizeObserver(([e]) => (h = e.contentRect.height));
		ro.observe(box);
		return () => ro.disconnect();
	});

	// Restore the saved view once we know how tall we are.
	$effect(() => {
		if (h <= 0 || initialised) return;
		initialised = true;
		let saved: { ppd?: number; scroll?: number; viewSpan?: ViewSpan } | null = null;
		try {
			const raw = localStorage.getItem(STORAGE_PREFIX + storageKey);
			saved = raw ? JSON.parse(raw) : null;
		} catch {
			saved = null;
		}
		if (saved) {
			if (saved.ppd) ppd = saved.ppd;
			if (saved.scroll != null) scroll = clampScroll(saved.scroll);
			if (saved.viewSpan) viewSpan = saved.viewSpan;
		} else {
			scroll = -h / (2 * ppd); // centre today
		}
		targetScroll = scroll;
		draw();
		selectCentre();
	});

	// Wheel is bound to the window (not the box) so a zoom gesture that starts
	// on the ruler is not stolen by the page scroller.
	$effect(() => {
		if (!box || h === 0) return;
		const el = box;

		function onWheel(e: WheelEvent) {
			if (!hovering) return;
			e.preventDefault();
			e.stopPropagation();
			const rect = el.getBoundingClientRect();
			if (e.ctrlKey) {
				if (spanCooldown) return;
				const cur = SPAN_ORDER.indexOf(viewSpan);
				const next = e.deltaY > 0 ? Math.max(0, cur - 1) : Math.min(SPAN_ORDER.length - 1, cur + 1);
				if (next !== cur) {
					viewSpan = SPAN_ORDER[next];
					spanCooldown = true;
					setTimeout(() => (spanCooldown = false), 300);
				}
				draw();
				selectCentre();
				persist();
			} else if (e.altKey || e.metaKey) {
				stopSmooth();
				const cy = e.clientY - rect.top;
				const cursorDA = scroll + (h - cy) / ppd;
				const factor = e.deltaY > 0 ? 0.85 : 1.18;
				ppd = Math.max(MIN_PPD, Math.min(MAX_PPD, ppd * factor));
				scroll = clampScroll(cursorDA - (h - cy) / ppd);
				targetScroll = scroll;
				draw();
				selectCentre();
				persist();
			} else {
				targetScroll = clampScroll(targetScroll - (e.deltaY * 0.5) / ppd);
				startSmooth();
			}
		}
		const onEnter = () => (hovering = true);
		const onLeave = () => (hovering = false);

		el.addEventListener('mouseenter', onEnter);
		el.addEventListener('mouseleave', onLeave);
		window.addEventListener('wheel', onWheel, { passive: false });
		return () => {
			el.removeEventListener('mouseenter', onEnter);
			el.removeEventListener('mouseleave', onLeave);
			window.removeEventListener('wheel', onWheel);
			stopSmooth();
		};
	});

	// Drag. Move/up live on the window so the gesture survives leaving the box.
	$effect(() => {
		if (!box || h === 0) return;
		const el = box;

		function onDown(e: MouseEvent) {
			stopSmooth();
			drag = { active: true, startY: e.clientY, startScroll: scroll, moved: false };
			targetScroll = scroll;
		}
		function onMove(e: MouseEvent) {
			if (!drag.active) return;
			const dy = e.clientY - drag.startY;
			if (Math.abs(dy) > 3) drag.moved = true;
			scroll = clampScroll(drag.startScroll - dy / ppd);
			targetScroll = scroll;
			draw();
			selectCentre();
		}
		function onUp(e: MouseEvent) {
			if (!drag.active) return;
			drag.active = false;
			persist();
			const rect = el.getBoundingClientRect();
			const inside =
				e.clientX >= rect.left &&
				e.clientX <= rect.right &&
				e.clientY >= rect.top &&
				e.clientY <= rect.bottom;
			if (!inside) startLabelAnim(0);
		}

		el.addEventListener('mousedown', onDown);
		window.addEventListener('mousemove', onMove);
		window.addEventListener('mouseup', onUp);
		return () => {
			el.removeEventListener('mousedown', onDown);
			window.removeEventListener('mousemove', onMove);
			window.removeEventListener('mouseup', onUp);
		};
	});

	// Touch: one finger scrolls, two pinch-zoom, double-tap cycles the span.
	$effect(() => {
		if (!box || h === 0) return;
		const el = box;
		let lastY = 0;
		let lastDist = 0;
		let active = false;
		let moved = false;
		let lastTap = 0;
		let fadeTimer: ReturnType<typeof setTimeout>;
		const DOUBLE_TAP_MS = 350;

		function onStart(e: TouchEvent) {
			e.preventDefault(); // no browser zoom on double-tap
			stopSmooth();
			startLabelAnim(1);
			moved = false;
			if (e.touches.length === 1) {
				lastY = e.touches[0].clientY;
				active = true;
			} else if (e.touches.length === 2) {
				active = false;
				lastDist = Math.hypot(
					e.touches[0].clientX - e.touches[1].clientX,
					e.touches[0].clientY - e.touches[1].clientY
				);
			}
			targetScroll = scroll;
		}
		function onMove(e: TouchEvent) {
			e.preventDefault();
			if (e.touches.length === 1 && active) {
				const dy = lastY - e.touches[0].clientY;
				if (Math.abs(dy) > 4) moved = true;
				lastY = e.touches[0].clientY;
				scroll = clampScroll(scroll + dy / ppd);
				targetScroll = scroll;
				draw();
				selectCentre();
			} else if (e.touches.length === 2 && lastDist > 0) {
				moved = true;
				const dist = Math.hypot(
					e.touches[0].clientX - e.touches[1].clientX,
					e.touches[0].clientY - e.touches[1].clientY
				);
				const midY = (e.touches[0].clientY + e.touches[1].clientY) / 2;
				const cy = midY - el.getBoundingClientRect().top;
				const cursorDA = scroll + (h - cy) / ppd;
				ppd = Math.max(MIN_PPD, Math.min(MAX_PPD, ppd * (dist / lastDist)));
				scroll = clampScroll(cursorDA - (h - cy) / ppd);
				targetScroll = scroll;
				lastDist = dist;
				draw();
				selectCentre();
			}
		}
		function onEnd(e: TouchEvent) {
			e.preventDefault();
			const wasActive = active;
			active = false;
			lastDist = 0;
			persist();
			clearTimeout(fadeTimer);
			fadeTimer = setTimeout(() => startLabelAnim(0), 800);

			if (!wasActive || moved || e.changedTouches.length !== 1) return;
			const now = Date.now();
			if (now - lastTap < DOUBLE_TAP_MS) {
				lastTap = 0;
				viewSpan = SPAN_ORDER[(SPAN_ORDER.indexOf(viewSpan) + 1) % SPAN_ORDER.length];
				persist();
				return;
			}
			lastTap = now;
		}

		el.addEventListener('touchstart', onStart, { passive: false });
		el.addEventListener('touchmove', onMove, { passive: false });
		el.addEventListener('touchend', onEnd, { passive: false });
		return () => {
			clearTimeout(fadeTimer);
			el.removeEventListener('touchstart', onStart);
			el.removeEventListener('touchmove', onMove);
			el.removeEventListener('touchend', onEnd);
		};
	});

	$effect(() => () => {
		if (labelAnim) cancelAnimationFrame(labelAnim);
		stopSmooth();
	});

	function onClick(e: MouseEvent) {
		if (drag.moved) {
			drag.moved = false;
			return;
		}
		if (!box) return;
		stopSmooth();
		targetScroll = scroll;
		const cy = e.clientY - box.getBoundingClientRect().top;
		const daysAgo = scroll + (h - cy) / ppd;
		const key = daToKey(Math.max(0, Math.round(daysAgo)));
		lastEmitted = key;
		onselect(key);
		persist();
	}
</script>

<div
	bind:this={box}
	role="slider"
	tabindex="0"
	aria-label="timeline"
	aria-valuenow={0}
	aria-valuetext={selected ?? 'no date selected'}
	class="relative h-full shrink-0 cursor-pointer touch-none outline-none select-none"
	style="width:{W}px"
	onmouseenter={() => {
		box?.focus({ preventScroll: true });
		startLabelAnim(1);
	}}
	onmouseleave={() => {
		if (!drag.active) startLabelAnim(0);
	}}
	onclick={onClick}
	onkeydown={(e) => {
		// Keyboard equivalent of dragging by a day.
		if (e.key !== 'ArrowUp' && e.key !== 'ArrowDown') return;
		e.preventDefault();
		stopSmooth();
		scroll = clampScroll(scroll + (e.key === 'ArrowUp' ? 1 : -1));
		targetScroll = scroll;
		draw();
		selectCentre();
		persist();
	}}
>
	<canvas bind:this={canvas} class="block" style="width:{W}px;height:{h || 0}px"></canvas>
	<!-- The reading head. Fixed at the vertical centre: the ruler moves, this
	     does not, and whatever it points at is the selection. -->
	<div class="pointer-events-none absolute left-0" style="top:50%;transform:translateY(-50%)">
		<svg width="10" height="14" viewBox="0 0 10 14">
			<path d="M0,0 L10,7 L0,14 Z" fill="#e7e5e4" />
		</svg>
	</div>
</div>
