<script lang="ts">
	/**
	 * The deck: a pile of days, the one on top, and the ways to take it off.
	 *
	 * ## Why this is not a scroll
	 *
	 * The album used to be one column of every day in the year, and it read as a
	 * feed rather than as a diary — the newest day got a photograph and three
	 * hundred others got a grey one-line row, because that is all a shared
	 * scroll can afford. A day at a time is the shape the writing actually has.
	 *
	 * ## The rule this keeps, restated
	 *
	 * **Scrolling was never the thing being refused — travelling by scrolling
	 * was.** The month rows, the chapter list and the jump field all still land
	 * on a page directly, so no day is more than one gesture away. Turning is
	 * the *adjacent* move and nothing else: a reader who wants a day in March
	 * does not turn to it, they jump, exactly as before.
	 *
	 * Scrolling *inside* a sheet is reading and is left alone.
	 *
	 * ## The sheet is this component's, and that is what makes a pile possible
	 *
	 * Every sheet is the same box: `absolute`, filling the deck, with its own
	 * scroll. `DayPage` prints on one and knows nothing about it. A component
	 * that was as tall as its own content — which is what the sheet used to be —
	 * can never stack, because a pile whose sheets are different sizes has no
	 * edges to draw, and two of them overlapping mid-turn would fight over the
	 * column's height. Same box for all of them means no measuring anywhere and
	 * a turn that is only transforms.
	 *
	 * ## The pile is real depth
	 *
	 * What stands behind the page is what is left to read — `stackBehind` in
	 * `log.ts`, capped where sheets stop being countable by eye. It thins as
	 * you go and thickens as you come back. The `n of m` counter underneath is
	 * not a second copy of that: the pile says *there is more*, the counter says
	 * *how much*, and only one of them can be read at a glance.
	 *
	 * ## One motion, three ways to ask for it
	 *
	 * A press on an edge, a drag, and the arrow keys all drive the same three
	 * states. That is the whole reason this is a small state machine rather than
	 * a `{#key}` block with a transition on it: a drag that finishes has to hand
	 * over to the animation a press starts, and two motions that nearly agree is
	 * how a screen like this ends up feeling wrong.
	 *
	 *   idle ──press / key──▶ settling ──▶ idle          (commits the index)
	 *   idle ──drag ──▶ dragging ──release──▶ settling ──▶ idle
	 *
	 * The top sheet always leaves the way you sent it and the next one always
	 * rises from the pile. Both directions, one shape: take a sheet off, the one
	 * under it comes up.
	 *
	 * **Transform and opacity only.** The `feDisplacementMap` that cost 23ms of
	 * every frame is the standing measurement in CLAUDE.md, and a pile drawn
	 * with an animated shadow would be that mistake in a new place. Reduced
	 * motion is honoured here rather than only in CSS, because the reduce block
	 * in `trophic.css` cannot reach a transform this file is setting.
	 */
	import DayPage from './DayPage.svelte';
	import { dayLabel, stackBehind, type Page } from './log';
	import type { Shot } from './media';
	import type { Entry } from './api';

	let {
		pages,
		index = $bindable(0),
		today = '',
		onopen,
		onholdmedia,
		onjump,
		ontoggle,
		onassign,
		held = ''
	}: {
		/** Newest page first, as everything in this app reads. */
		pages: Page[];
		index?: number;
		/** Today's day key, so the page for it can say so. */
		today?: string;
		onopen?: (shots: Shot[], index: number) => void;
		onholdmedia?: (ref: string, x: number, y: number) => void;
		onjump?: (entryId: string) => void;
		ontoggle?: (entry: Entry, line: number) => void;
		onassign?: (entry: Entry, x: number, y: number) => void;
		held?: string;
	} = $props();

	/** Clamped on the way out rather than on the way in: the deck changes under
	 *  this component whenever the scope filter does, and an index left pointing
	 *  past the end of a shorter deck would draw nothing at all. */
	const at = $derived(Math.min(Math.max(index, 0), Math.max(pages.length - 1, 0)));
	const current = $derived(pages[at] ?? null);

	/** Newest first, so a *higher* index is further back. */
	const older = $derived(pages[at + 1] ?? null);
	const newer = $derived(pages[at - 1] ?? null);

	/** Where the pile stops being countable. Four sheets and forty say the same
	 *  thing at a glance; the counter says the rest. */
	const PILE = 4;
	/** How far the sheet has to go before the turn takes. A quarter of the
	 *  sheet: far enough that a flick while reading does not turn a page,
	 *  near enough that a deliberate one never has to be finished by hand. */
	const TAKES = 0.25;
	/** Past `LONG_PRESS_MOVE` (10px, `longpress.ts`), so a hold has already
	 *  cancelled itself by the time a drag begins and the two gestures never
	 *  both fire. */
	const DRAG_START = 12;
	const SETTLE = 260;

	let box = $state<HTMLElement | null>(null);
	/** `idle`, or a turn in flight. */
	let phase = $state<'idle' | 'dragging' | 'settling'>('idle');
	/** The turn being made: which way, and the page it lands on. */
	let moving = $state<{ dir: 'older' | 'newer'; to: number } | null>(null);
	/** The live offset of the top sheet, in pixels. The finger writes this
	 *  while dragging and the settle animates it. */
	let dx = $state(0);
	/** Measured once per gesture rather than per frame — the sheet does not
	 *  resize mid-turn, and reading `clientWidth` in a pointermove is a layout
	 *  pass on every one of them. */
	let width = $state(1);
	let timer: ReturnType<typeof setTimeout> | undefined;

	const reduced = () =>
		typeof window !== 'undefined' &&
		window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

	/** The page arriving, mounted only while a turn is live. One extra
	 *  `DayPage` for the length of a turn is the same cost the cross-fade this
	 *  replaces was already paying. */
	const incoming = $derived(moving ? (pages[moving.to] ?? null) : null);

	/** How far through the turn we are, 0 → 1. */
	const progress = $derived(Math.min(1, Math.abs(dx) / Math.max(width, 1)));

	/** The pile, as drawn. One sheet short while a page is rising *out* of it:
	 *  its top sheet is the incoming page, which is already on screen. */
	const behind = $derived(stackBehind(pages.length, at, PILE));
	const pile = $derived(Math.max(0, behind - (moving?.dir === 'older' ? 1 : 0)));

	function commit(to: number | null) {
		clearTimeout(timer);
		phase = 'idle';
		moving = null;
		dx = 0;
		// Last, so the sheets are back at rest before the deck changes under
		// them: the incoming node is keyed on its page, so it is *kept* and
		// simply becomes the top sheet where it already is.
		if (to !== null) index = to;
	}

	/** Start a turn that finishes on its own. The press and the keys both use
	 *  this; a released drag joins at `settle`. */
	function go(to: 'older' | 'newer') {
		if (phase !== 'idle') return;
		const next = to === 'older' ? at + 1 : at - 1;
		if (next < 0 || next >= pages.length) return;
		if (reduced()) {
			index = next;
			return;
		}
		width = box?.clientWidth ?? 1;
		dx = 0;
		moving = { dir: to, to: next };
		phase = 'settling';
		// A frame at rest first, or the transition has nothing to run from.
		requestAnimationFrame(() => {
			if (phase === 'settling') dx = to === 'older' ? -width : width;
		});
		timer = setTimeout(() => commit(next), SETTLE + 20);
	}

	/** Finish or abandon the turn the finger was making. */
	function settle(take: boolean) {
		const to = take && moving ? moving.to : null;
		if (reduced()) {
			commit(to);
			return;
		}
		phase = 'settling';
		dx = take && moving ? (moving.dir === 'older' ? -width : width) : 0;
		timer = setTimeout(() => commit(to), SETTLE + 20);
	}

	// ── The drag ──────────────────────────────────────────────────────────
	//
	// Claimed only once the movement is unambiguously sideways: `touch-action:
	// pan-y` leaves vertical scrolling to the browser, and the axis bias is
	// what stops reading a long page from turning it.
	let from: { x: number; y: number; id: number } | null = null;
	/** Set by a drag, cleared by the one click it would otherwise produce.
	 *  Dragging off a photograph must not also open it. */
	let dragged = false;

	/** Keeping the pointer, and letting it go. Wrapped because a pointer can be
	 *  gone by the time we ask for it — lifted, cancelled by the system, or
	 *  synthesised by a test — and the browser throws rather than shrugging.
	 *  Losing the capture costs nothing here: the handlers are on the box the
	 *  gesture started in. */
	function capture(take: boolean, id: number) {
		try {
			if (take) box?.setPointerCapture(id);
			else box?.releasePointerCapture(id);
		} catch {
			/* the pointer is already gone */
		}
	}

	function down(event: PointerEvent) {
		if (phase !== 'idle') return;
		if (event.pointerType === 'mouse' && event.button !== 0) return;
		from = { x: event.clientX, y: event.clientY, id: event.pointerId };
	}

	function move(event: PointerEvent) {
		if (!from || event.pointerId !== from.id) return;
		const mx = event.clientX - from.x;
		const my = event.clientY - from.y;
		if (phase === 'idle') {
			if (Math.abs(mx) < DRAG_START || Math.abs(mx) < Math.abs(my) * 1.5) return;
			const dir = mx < 0 ? 'older' : 'newer';
			const next = dir === 'older' ? at + 1 : at - 1;
			if (next < 0 || next >= pages.length) {
				from = null;
				return;
			}
			width = box?.clientWidth ?? 1;
			moving = { dir, to: next };
			phase = 'dragging';
			dragged = true;
			capture(true, event.pointerId);
		}
		if (phase !== 'dragging') return;
		dx = mx;
	}

	function up(event: PointerEvent) {
		if (from && event.pointerId === from.id) from = null;
		if (phase !== 'dragging') return;
		capture(false, event.pointerId);
		// Far enough, and still going the way the turn was claimed for — a drag
		// that crossed the threshold and then came back the other way has
		// changed its mind, and the sheet it would land on is not the one it
		// set out for.
		const far = Math.abs(dx) / Math.max(width, 1) > TAKES;
		const same = moving ? (moving.dir === 'older' ? dx < 0 : dx > 0) : false;
		settle(far && same);
	}

	function swallow(event: MouseEvent) {
		if (!dragged) return;
		dragged = false;
		event.preventDefault();
		event.stopPropagation();
	}

	function onKey(event: KeyboardEvent) {
		if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
		if (event.metaKey || event.ctrlKey || event.altKey) return;
		// What has focus, not what the event was aimed at: an arrow pressed with
		// no focus at all arrives on `document`, which has no `closest` — asking
		// it for one throws, and the handler dies before it ever turns a page.
		// `activeElement` is also the more honest question: a cursor in a field
		// is the only thing an arrow means there, wherever the event was raised.
		const focused = document.activeElement;
		if (focused instanceof HTMLElement && focused.closest('input, textarea, [contenteditable="true"]')) {
			return;
		}
		go(event.key === 'ArrowLeft' ? 'older' : 'newer');
	}

	/** `Sat 15 Aug`, or `Sat 15 Aug 2/3` when the day it leads to continues. */
	function edgeLabel(page: Page): string {
		const label = dayLabel(page.day.key);
		return page.parts > 1 ? `${label} ${page.part + 1}/${page.parts}` : label;
	}

	/** The sheet leaving: it goes the way it was sent and thins as it does. */
	const topStyle = $derived(
		`transform:translateX(${dx}px) rotate(${(dx / Math.max(width, 1)) * 1.2}deg);` +
			`opacity:${1 - progress * 0.9};` +
			(phase === 'settling' ? `transition:transform ${SETTLE}ms var(--ease-sheet), opacity ${SETTLE}ms var(--ease-sheet);` : '')
	);

	/** And the one under it comes up out of the pile. */
	const riseStyle = $derived(
		`transform:translate(${(1 - progress) * 5}px, ${(1 - progress) * 7}px) scale(${1 - (1 - progress) * 0.006});` +
			`opacity:${0.55 + progress * 0.45};` +
			(phase === 'settling' ? `transition:transform ${SETTLE}ms var(--ease-sheet), opacity ${SETTLE}ms var(--ease-sheet);` : '')
	);

	/** **One keyed list, not two blocks.** The arriving sheet and the leaving
	 *  one have to be the same `{#each}` for the commit to be free: keyed on
	 *  the page, Svelte *keeps* the arriving node when the index changes under
	 *  it and drops the other, so the sheet stays exactly where it animated to.
	 *  Two separate blocks would destroy it and build the same page again — a
	 *  flash, and a `DayPage` rebuilt for nothing.
	 *
	 *  The leaving sheet is last, so it paints over the one coming up. */
	const sheets = $derived([
		...(incoming ? [{ page: incoming, style: riseStyle }] : []),
		...(current ? [{ page: current, style: topStyle }] : [])
	]);
</script>

<svelte:window onkeydown={onKey} />

{#snippet edge(to: 'older' | 'newer', target: Page | null)}
	<!-- Held open whether or not it can be pressed, so the page underneath does
	     not shift sideways by a gutter at the ends of the deck.

	     Narrow below `lg`, which is where a tablet in portrait lives. Two 74px
	     gutters plus the index left an iPad about 210px of page — a date
	     stacked three words high. The arrow is the part that has to survive;
	     the date beside it is what goes, because at that width the page's own
	     headline is already saying the day. -->
	<button
		type="button"
		class="group/edge flex w-[30px] shrink-0 flex-col items-center justify-center gap-3 transition-colors lg:w-[64px]
		       {target ? 'hover:bg-neutral-200/60' : 'pointer-events-none opacity-0'}"
		disabled={!target}
		aria-label={target ? `${to === 'older' ? 'earlier' : 'later'}: ${edgeLabel(target)}` : undefined}
		onclick={() => go(to)}
	>
		<span
			class="text-[22px] leading-none text-neutral-600 transition-colors group-hover/edge:text-ink"
		>
			{to === 'older' ? '‹' : '›'}
		</span>
		{#if target}
			<!-- The date it leads to, standing up. A turn is worth making with the
			     day in front of you rather than after you have made it. -->
			<span
				class="hidden text-[11px] tracking-[0.08em] text-neutral-600 transition-colors group-hover/edge:text-neutral-800 lg:inline"
				style="writing-mode:vertical-rl;{to === 'older' ? 'transform:rotate(180deg)' : ''}"
			>
				{edgeLabel(target)}
			</span>
		{/if}
	</button>
{/snippet}

{#if current}
	<div class="flex min-h-0 flex-1 items-stretch gap-1">
		{@render edge('older', older)}

		<!-- The deck. The right and bottom padding is where the pile lies: the
		     sheets are inset by exactly that much, so the stack has somewhere to
		     be without overhanging a column that clips it. -->
		<!-- A region rather than a bare box: it takes a drag, so it has to say
		     what it is to anything that is not a pointer. The edges either side
		     are the controls; this is the thing they act on. -->
		<div
			bind:this={box}
			role="region"
			aria-label="the open page — drag sideways to turn"
			class="relative mx-auto min-w-0 flex-1 pr-[22px] pb-[30px] {phase === 'dragging'
				? 'select-none'
				: ''}"
			style="max-width:882px;touch-action:pan-y"
			onpointerdown={down}
			onpointermove={move}
			onpointerup={up}
			onpointercancel={up}
			onclickcapture={swallow}
		>
			<!-- What is left to read, as edges. Deepest first so the nearest
			     paints last, and inert: the pile is a fact, not a control. -->
			{#each Array(pile) as _, i (i)}
				{@const d = pile - i}
				<div
					aria-hidden="true"
					class="sheet pointer-events-none"
					style="transform:translate({d * 5}px, {d * 7}px) scale({1 - d * 0.006});
					       opacity:{1 - d * 0.14};transition:transform {SETTLE}ms var(--ease-sheet)"
				></div>
			{/each}

			<!-- The page rising out of the pile, then the one leaving over it. -->
			{#each sheets as sheet (sheet.page.key)}
				<div class="sheet" style={sheet.style}>
					<DayPage
						page={sheet.page}
						today={sheet.page.day.key === today}
						{onopen}
						{onholdmedia}
						{onjump}
						{ontoggle}
						{onassign}
						{held}
					/>
				</div>
			{/each}
		</div>

		{@render edge('newer', newer)}
	</div>

	<!-- Where you are in the deck. A page count rather than a scrollbar: a deck
	     has a length you can state, and stating it is what a scrollbar was only
	     ever approximating. -->
	<div
		class="flex shrink-0 items-center justify-center gap-2 pt-2 text-[11px] text-neutral-600 tabular-nums"
	>
		<span>{at + 1} of {pages.length}</span>
	</div>
{/if}

<style>
	/* Every sheet is the same box. `inset` rather than a height, because the
	   deck's own padding is where the pile lies. */
	.sheet {
		position: absolute;
		top: 0;
		left: 0;
		right: 22px;
		bottom: 30px;
		overflow-y: auto;
		border-radius: 18px;
		background: var(--color-surface);
		box-shadow: inset 0 0 0 1px var(--color-neutral-400);
	}
</style>
