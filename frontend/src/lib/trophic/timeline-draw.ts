// The log's date ruler, drawn on a canvas. Ported from `hooks/timeline-draw.ts`.
//
// Structure is unchanged — same four zoom regimes (day / week / month / year
// ticks, chosen by pixels-per-day), same rule that a tick is "prominent" if
// its unit has entries or is today or is the oldest thing you have written.
// Only the colours moved, from the source's zinc-on-white to warm greys on
// this app's #14100c. Every literal below had a light-theme twin in the
// original; see colors.ts for the reasoning.

export type ViewSpan = 'day' | 'week' | 'month';

const SPAN_DAYS: Record<ViewSpan, number> = { day: 1, week: 7, month: 30 };

// Warm equivalents of the source's zinc ramp.
// One rung brighter than a straight translation of the source's zinc greys:
// #e4e4e7 on white is a hairline you can just see, and its literal warm
// equivalent on #14100c disappeared entirely when rendered.
const C = {
	track: '#403830',
	dayTick: '#4a4038',
	unitTick: '#5d5045',
	selected: '#e7e5e4'
};
const LABEL_RGB = '168,162,158'; // stone-400
const DAYNUM_RGB = '124,116,108'; // stone-500, a shade warmer

function da(todayMs: number, dateStr: string): number {
	const [y, m, d] = dateStr.split('-').map(Number);
	return Math.round((todayMs - Date.UTC(y, m - 1, d)) / 86400000);
}

function daToKey(todayMs: number, n: number): string {
	return new Date(todayMs - n * 86400000).toISOString().slice(0, 10);
}

function daToDate(todayMs: number, n: number): Date {
	return new Date(todayMs - n * 86400000);
}

export type DrawParams = {
	ctx: CanvasRenderingContext2D;
	W: number;
	h: number;
	ppd: number;
	scroll: number;
	labelAlpha: number;
	dates: Record<string, number>;
	selected: string | null;
	viewSpan: ViewSpan;
	todayMs: number;
	/** Denser intermediate ticks, and labels always on (touch has no hover). */
	dense?: boolean;
};

// Dim multiplier for empty units in dense mode — keeps the grid legible while
// letting days with entries dominate.
const DIM_ALPHA = 0.25;

export function drawTimeline(p: DrawParams) {
	const { ctx, W, h, ppd, scroll, dates, selected, viewSpan, todayMs, dense } = p;
	const la = dense ? 1 : p.labelAlpha;

	ctx.clearRect(0, 0, W, h);

	const bottomDA = scroll;
	const topDA = scroll + h / ppd;
	const lineX = W - 8;

	const y = (daysAgo: number) => h - (daysAgo - scroll) * ppd;

	ctx.strokeStyle = C.track;
	ctx.lineWidth = 1;
	ctx.beginPath();
	ctx.moveTo(lineX, 0);
	ctx.lineTo(lineX, h);
	ctx.stroke();

	// ── Which units have entries ─────────────────────────────
	const dateKeys = Object.keys(dates);
	const monthsWithEntries = new Set<string>();
	const weeksWithEntries = new Set<string>();
	const yearsWithEntries = new Set<string>();
	for (const k of dateKeys) {
		monthsWithEntries.add(k.slice(0, 7));
		yearsWithEntries.add(k.slice(0, 4));
		const d = da(todayMs, k);
		const dayOfWeek = daToDate(todayMs, d).getUTCDay() || 7;
		weeksWithEntries.add(String(d + (dayOfWeek - 1)));
	}
	const oldestKey = dateKeys.length > 0 ? dateKeys.reduce((a, b) => (a < b ? a : b)) : null;
	const oldestDA = oldestKey ? da(todayMs, oldestKey) : -1;

	ctx.font = '9px monospace';
	ctx.textAlign = 'right';
	ctx.textBaseline = 'middle';

	const lo = Math.max(0, Math.floor(bottomDA) - 1);
	const hi = Math.ceil(topDA) + 1;
	const base = { lineX, la, h, todayMs, dense: !!dense, y };

	if (ppd >= 8) {
		drawDayTicks(ctx, { ...base, lo, hi, dates, oldestDA, monthsWithEntries });
	} else if (ppd >= 2) {
		drawWeekTicks(ctx, { ...base, lo, hi, weeksWithEntries, oldestDA });
	} else if (ppd >= 0.2) {
		drawMonthTicks(ctx, { ...base, topDA, bottomDA, monthsWithEntries, oldestKey });
	} else {
		drawYearTicks(ctx, { ...base, topDA, bottomDA, yearsWithEntries, oldestKey });
	}

	// ── Dense intermediate ticks (touch) ─────────────────────
	if (dense) {
		ctx.strokeStyle = C.dayTick;
		ctx.lineWidth = 0.3;
		let interval: number;
		if (ppd >= 2) interval = 1;
		else if (ppd >= 0.1) interval = 7;
		else interval = 30;

		const dLo = Math.max(0, Math.floor(bottomDA));
		const dHi = Math.ceil(topDA);
		for (let d = dLo - (dLo % interval); d <= dHi; d += interval) {
			if (d < 0) continue;
			const yy = y(d);
			if (yy < 0 || yy > h) continue;
			ctx.beginPath();
			ctx.moveTo(lineX - 2, yy);
			ctx.lineTo(lineX + 2, yy);
			ctx.stroke();
		}
	}

	// ── Centre line: what the arrow points at ────────────────
	{
		const centerY = h / 2;
		ctx.strokeStyle = '#57534e';
		ctx.lineWidth = 0.5;
		ctx.setLineDash([3, 3]);
		ctx.beginPath();
		ctx.moveTo(10, centerY);
		ctx.lineTo(W, centerY);
		ctx.stroke();
		ctx.setLineDash([]);
	}

	// ── Selected day, or the selected span as a band ─────────
	if (selected) {
		const daysAgo = da(todayMs, selected);
		const spanDays = SPAN_DAYS[viewSpan];

		if (spanDays <= 1) {
			const yy = y(daysAgo);
			if (yy >= 0 && yy <= h) {
				ctx.strokeStyle = C.selected;
				ctx.lineWidth = 1;
				ctx.setLineDash([2, 2]);
				ctx.beginPath();
				ctx.moveTo(0, yy);
				ctx.lineTo(W, yy);
				ctx.stroke();
				ctx.setLineDash([]);
			}
		} else {
			const yBottom = y(daysAgo);
			const yTop = y(daysAgo + spanDays - 1);
			const areaTop = Math.max(0, Math.min(yTop, yBottom));
			const areaBottom = Math.min(h, Math.max(yTop, yBottom));
			if (areaBottom > 0 && areaTop < h) {
				ctx.fillStyle = 'rgba(231,229,228,0.07)';
				ctx.fillRect(0, areaTop, W, areaBottom - areaTop);
				ctx.strokeStyle = C.selected;
				ctx.lineWidth = 1;
				ctx.setLineDash([2, 2]);
				ctx.beginPath();
				ctx.moveTo(0, areaTop);
				ctx.lineTo(W, areaTop);
				ctx.moveTo(0, areaBottom);
				ctx.lineTo(W, areaBottom);
				ctx.stroke();
				ctx.setLineDash([]);
			}
		}
	}
}

type TickCtx = {
	lineX: number;
	la: number;
	h: number;
	todayMs: number;
	dense: boolean;
	y: (daysAgo: number) => number;
};

function drawDayTicks(
	ctx: CanvasRenderingContext2D,
	p: TickCtx & {
		lo: number;
		hi: number;
		dates: Record<string, number>;
		oldestDA: number;
		monthsWithEntries: Set<string>;
	}
) {
	for (let d = p.lo; d <= p.hi; d++) {
		const key = daToKey(p.todayMs, d);
		const hasEntries = !!p.dates[key];
		const isToday = d === 0;
		const isOldest = d === p.oldestDA;
		const prominent = hasEntries || isToday || isOldest;
		if (!p.dense && !prominent) continue;

		const yy = p.y(d);
		if (yy < -10 || yy > p.h + 10) continue;

		const a = prominent ? p.la : p.la * DIM_ALPHA;

		ctx.strokeStyle = C.dayTick;
		ctx.lineWidth = 0.5;
		ctx.beginPath();
		ctx.moveTo(p.lineX - 3, yy);
		ctx.lineTo(p.lineX + 3, yy);
		ctx.stroke();

		if (a > 0.01) {
			const date = daToDate(p.todayMs, d);
			if (isToday) {
				ctx.fillStyle = `rgba(${LABEL_RGB},${a})`;
				ctx.fillText('now', p.lineX - 5, yy);
			} else if (date.getUTCDate() === 1) {
				if (p.dense || p.monthsWithEntries.has(key.slice(0, 7)) || isOldest) {
					ctx.fillStyle = `rgba(${LABEL_RGB},${a})`;
					ctx.fillText(
						date.toLocaleDateString(undefined, { month: 'short', timeZone: 'UTC' }),
						p.lineX - 5,
						yy
					);
				}
			} else {
				ctx.fillStyle = `rgba(${DAYNUM_RGB},${a})`;
				ctx.fillText(String(date.getUTCDate()), p.lineX - 5, yy);
			}
		}
	}
}

function drawWeekTicks(
	ctx: CanvasRenderingContext2D,
	p: TickCtx & { lo: number; hi: number; weeksWithEntries: Set<string>; oldestDA: number }
) {
	for (let d = p.lo; d <= p.hi; d++) {
		const date = daToDate(p.todayMs, d);
		const isToday = d === 0;
		if (date.getUTCDay() !== 1 && !isToday) continue;

		const mondayDA = isToday ? d + ((date.getUTCDay() || 7) - 1) : d;
		const weekHasEntries = p.weeksWithEntries.has(String(mondayDA));
		const isOldest = p.oldestDA >= 0 && d >= p.oldestDA && d <= p.oldestDA + 6;
		const prominent = weekHasEntries || isToday || isOldest;
		if (!p.dense && !prominent) continue;

		const yy = p.y(d);
		if (yy < -10 || yy > p.h + 10) continue;

		const a = prominent ? p.la : p.la * DIM_ALPHA;

		ctx.strokeStyle = C.unitTick;
		ctx.lineWidth = 0.5;
		ctx.beginPath();
		ctx.moveTo(p.lineX - 4, yy);
		ctx.lineTo(p.lineX + 4, yy);
		ctx.stroke();

		if (a > 0.01) {
			ctx.fillStyle = `rgba(${LABEL_RGB},${a})`;
			ctx.fillText(
				isToday
					? 'now'
					: date.toLocaleDateString(undefined, {
							month: 'short',
							day: 'numeric',
							timeZone: 'UTC'
						}),
				p.lineX - 5,
				yy
			);
		}
	}
}

function drawMonthTicks(
	ctx: CanvasRenderingContext2D,
	p: TickCtx & {
		topDA: number;
		bottomDA: number;
		monthsWithEntries: Set<string>;
		oldestKey: string | null;
	}
) {
	const oldestVis = daToDate(p.todayMs, Math.ceil(p.topDA));
	const newestVis = daToDate(p.todayMs, Math.max(0, Math.floor(p.bottomDA)));
	const cur = new Date(Date.UTC(oldestVis.getUTCFullYear(), oldestVis.getUTCMonth(), 1));
	const oldestMonthKey = p.oldestKey ? p.oldestKey.slice(0, 7) : null;
	const todayMonthKey = daToKey(p.todayMs, 0).slice(0, 7);

	while (cur <= newestVis) {
		const monthKey = `${cur.getUTCFullYear()}-${String(cur.getUTCMonth() + 1).padStart(2, '0')}`;
		const prominent =
			p.monthsWithEntries.has(monthKey) ||
			monthKey === todayMonthKey ||
			monthKey === oldestMonthKey;

		if (!p.dense && !prominent) {
			cur.setUTCMonth(cur.getUTCMonth() + 1);
			continue;
		}

		const daysAgo = Math.round((p.todayMs - cur.getTime()) / 86400000);
		const yy = p.y(daysAgo);
		if (yy >= -10 && yy <= p.h + 10) {
			const a = prominent ? p.la : p.la * DIM_ALPHA;
			ctx.strokeStyle = C.unitTick;
			ctx.lineWidth = 0.5;
			ctx.beginPath();
			ctx.moveTo(p.lineX - 4, yy);
			ctx.lineTo(p.lineX + 4, yy);
			ctx.stroke();
			if (a > 0.01) {
				ctx.fillStyle = `rgba(${LABEL_RGB},${a})`;
				ctx.fillText(
					cur.toLocaleDateString(undefined, { month: 'short', timeZone: 'UTC' }),
					p.lineX - 5,
					yy
				);
			}
		}
		cur.setUTCMonth(cur.getUTCMonth() + 1);
	}
}

function drawYearTicks(
	ctx: CanvasRenderingContext2D,
	p: TickCtx & {
		topDA: number;
		bottomDA: number;
		yearsWithEntries: Set<string>;
		oldestKey: string | null;
	}
) {
	const oldestVis = daToDate(p.todayMs, Math.ceil(p.topDA));
	const newestVis = daToDate(p.todayMs, Math.max(0, Math.floor(p.bottomDA)));
	const todayYear = String(newestVis.getUTCFullYear());
	const oldestYear = p.oldestKey ? p.oldestKey.slice(0, 4) : null;

	for (let yr = oldestVis.getUTCFullYear(); yr <= newestVis.getUTCFullYear(); yr++) {
		const yrStr = String(yr);
		const prominent =
			p.yearsWithEntries.has(yrStr) || yrStr === todayYear || yrStr === oldestYear;
		if (!p.dense && !prominent) continue;

		const daysAgo = Math.round((p.todayMs - Date.UTC(yr, 0, 1)) / 86400000);
		const yy = p.y(daysAgo);
		if (yy >= -10 && yy <= p.h + 10) {
			const a = prominent ? p.la : p.la * DIM_ALPHA;
			ctx.strokeStyle = C.unitTick;
			ctx.lineWidth = 0.5;
			ctx.beginPath();
			ctx.moveTo(p.lineX - 4, yy);
			ctx.lineTo(p.lineX + 4, yy);
			ctx.stroke();
			if (a > 0.01) {
				ctx.fillStyle = `rgba(${LABEL_RGB},${a})`;
				ctx.fillText(yrStr, p.lineX - 5, yy);
			}
		}
	}
}
