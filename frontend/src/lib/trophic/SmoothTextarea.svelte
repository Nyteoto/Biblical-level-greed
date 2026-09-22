<script lang="ts">
	/**
	 * The capture bar's input. Ported from `components/SmoothTextarea.tsx`.
	 *
	 * CAPTURE-BAR.md says this is the piece to get right first, and why: the
	 * native caret is switched off (`caret-color: transparent`) and replaced by
	 * a div that is *measured* off a zero-width marker injected into the
	 * coloured overlay, then translated to that point over 80ms linear. It
	 * glides; it does not jump. That glide is the signature of the whole input,
	 * and a plain <textarea> with a native caret makes everything else here
	 * cosmetic by comparison.
	 *
	 * The architecture that requires: a real textarea for input and IME, a
	 * coloured overlay for display, a marker to measure, and a separately
	 * positioned caret. The two layers must share their text metrics exactly —
	 * hence `.smooth-layout` on both — or the caret drifts along a line.
	 *
	 * **What this file is, and is not.** Everything decidable without a DOM
	 * lives in `capture-bar.ts`, where `capture_overlay.json` (26 cases) and
	 * `capture_keys.json` (18) are replayed against it. What is left here is
	 * the part only a browser can do: the textarea, the measuring, the timers,
	 * and the focus. Anything added below that decides *what the bar shows or
	 * what a key means* belongs in the module instead, or the corpus stops
	 * being able to see it.
	 *
	 * Blinking stops while you type and resumes 530ms after the last keystroke:
	 * a caret that blinks mid-word reads as an idle terminal.
	 */
	import { tick } from 'svelte';
	import {
		view,
		handleKey,
		caretStyle,
		acceptSuggestion,
		rankedSuggestions,
		BLINK_PAUSE_MS,
		type BarState
	} from './capture-bar';
	import { loadStats, saveStats, type UsageStats } from './trie';
	import { toRamp } from './colors';
	import type { Vocab } from './api';

	let {
		value = $bindable(''),
		vocab,
		placeholder = '',
		blinkIndices = [],
		onkeydown,
		onpaste,
		onfocus,
		onblur
	}: {
		value: string;
		vocab?: Vocab;
		placeholder?: string;
		/** Token indices that should blink red — set by validation. */
		blinkIndices?: number[];
		onkeydown?: (e: KeyboardEvent) => void;
		onpaste?: (e: ClipboardEvent) => void;
		onfocus?: () => void;
		onblur?: () => void;
	} = $props();

	let ta = $state<HTMLTextAreaElement | null>(null);
	let wrapper = $state<HTMLDivElement | null>(null);
	let overlay = $state<HTMLDivElement | null>(null);
	let marker = $state<HTMLSpanElement | null>(null);

	let caret = $state(0);
	/** The selection, in characters of `value`. Equal when there is none. */
	let selStart = $state(0);
	let selEnd = $state(0);
	/** Where the selection is on screen, one rectangle per line it covers. */
	let selRects = $state<{ x: number; y: number; w: number; h: number }[]>([]);
	let focused = $state(false);
	let suggestIdx = $state(0);
	let stats = $state<UsageStats>({});
	let caretPos = $state<{ x: number; y: number } | null>(null);
	let caretScreen = $state<{ x: number; y: number } | null>(null);
	let blinking = $state(true);
	let blinkTimer: ReturnType<typeof setTimeout>;

	const barState = $derived<BarState>({ value, caret, suggestIdx, stats });
	const bar = $derived(view(barState, vocab, blinkIndices));

	function pauseBlink() {
		blinking = false;
		clearTimeout(blinkTimer);
		blinkTimer = setTimeout(() => (blinking = true), BLINK_PAUSE_MS);
	}

	export function focus() {
		ta?.focus();
	}

	/** Type `text` at the caret, replacing any selection. With `close`, the
	 *  pair goes *around* the selection instead — or, with nothing selected,
	 *  either side of the caret, which lands between them: a `<>` key that
	 *  left you after the `>` would have you arrowing back to write the tag. */
	export function insertText(text: string, close = '') {
		if (!ta) return;
		ta.focus();
		const start = ta.selectionStart;
		const end = ta.selectionEnd;
		const inside = close ? value.slice(start, end) : '';
		const nextCaret = close && inside ? start + text.length + inside.length + close.length : start + text.length;
		value = value.slice(0, start) + text + inside + close + value.slice(end);
		requestAnimationFrame(() => {
			ta?.setSelectionRange(nextCaret, nextCaret);
			syncCaret();
		});
	}

	function syncCaret() {
		if (!ta) return;
		caret = ta.selectionStart ?? 0;
		selStart = ta.selectionStart ?? 0;
		selEnd = ta.selectionEnd ?? 0;
	}

	/** Apply a new bar state and put the real selection where it says. */
	function applyState(next: BarState) {
		value = next.value;
		suggestIdx = next.suggestIdx;
		if (next.stats !== stats) {
			stats = next.stats;
			saveStats(stats);
		}
		requestAnimationFrame(() => {
			if (!ta) return;
			ta.focus();
			ta.setSelectionRange(next.caret, next.caret);
			syncCaret();
		});
	}

	// iOS loupe drag and Android handle drag fire `selectionchange` on the
	// document continuously but do not fire `select` on the textarea until
	// release. Listening here is what makes the fake caret track the finger
	// instead of teleporting on lift.
	$effect(() => {
		function onSel() {
			if (document.activeElement === ta) syncCaret();
		}
		document.addEventListener('selectionchange', onSel);
		return () => document.removeEventListener('selectionchange', onSel);
	});

	$effect(() => {
		stats = loadStats();
	});

	$effect(() => () => clearTimeout(blinkTimer));

	// Auto-grow, then measure the caret off the marker. Both read `value` and
	// `caret` so they re-run together; measuring happens after Svelte has
	// flushed the DOM, which is the equivalent of the source's layout effect.
	$effect(() => {
		void value;
		if (!ta) return;
		ta.style.height = 'auto';
		ta.style.height = `${ta.scrollHeight}px`;
	});

	/**
	 * Where a character offset lands in the overlay's text.
	 *
	 * The overlay is a run of spans and one zero-width marker — the thing the
	 * caret is measured from — and that marker is a character in the DOM and no
	 * characters of `value`, so it is stepped over rather than counted. Get that
	 * wrong and the highlight is off by one from wherever the caret is.
	 */
	function locate(offset: number): { node: Node; at: number } | null {
		if (!overlay) return null;
		const walk = document.createTreeWalker(overlay, NodeFilter.SHOW_TEXT);
		let seen = 0;
		let node = walk.nextNode();
		while (node) {
			if (!marker?.contains(node)) {
				const len = node.textContent?.length ?? 0;
				if (seen + len >= offset) return { node, at: offset - seen };
				seen += len;
			}
			node = walk.nextNode();
		}
		return null;
	}

	/**
	 * The selection, drawn rather than left to the browser.
	 *
	 * The same argument as the caret two layers up: what is selected is the
	 * *textarea*, whose glyphs are transparent because the coloured ones belong
	 * to the overlay underneath it — so the native highlight paints a block over
	 * the overlay and takes the words with it, and `::selection { color }` does
	 * not reliably bring them back on an element whose own colour is
	 * `transparent`. WebKit is the engine that does not, and WebKit is what this
	 * app is read in.
	 *
	 * So the native one is switched off in the styles below, exactly as the
	 * caret is, and the highlight is measured off the overlay with a DOM range
	 * and painted *under* the text. Under, not over, is the other half of the
	 * point: the syntax colouring stays visible through a selection, which is
	 * the whole reason this bar has an overlay in the first place.
	 *
	 * One rectangle per line, because that is what `getClientRects` gives a
	 * range that wraps — and it costs nothing when there is no selection, which
	 * is almost always.
	 */
	$effect(() => {
		void value;
		void selStart;
		void selEnd;
		void focused;
		if (!wrapper || !overlay || !focused || selEnd <= selStart) {
			selRects = [];
			return;
		}
		const from = locate(selStart);
		const to = locate(selEnd);
		if (!from || !to) {
			selRects = [];
			return;
		}
		const range = document.createRange();
		range.setStart(from.node, from.at);
		range.setEnd(to.node, to.at);
		const box = wrapper.getBoundingClientRect();
		// One band per line, not one per span. A range across coloured tokens
		// comes back as a rectangle for every text node it touches — a dozen of
		// them for one dragged line, several of them empty — so they are merged
		// on their vertical position, which is what makes a line.
		//
		// The band is the *line's* height rather than the glyphs': the rects a
		// range gives are the height of the type, so using them raw leaves a
		// stripe of unhighlighted ground between wrapped lines.
		// Off the overlay, which is the layer that carries the text metrics —
		// the wrapper has no line-height of its own and answers `normal`.
		const line = parseFloat(getComputedStyle(overlay).lineHeight) || 0;
		const bands = new Map<number, { x: number; right: number; y: number; h: number }>();
		for (const r of range.getClientRects()) {
			if (r.width <= 0) continue;
			const key = Math.round(r.top);
			const found = bands.get(key);
			if (found) {
				found.x = Math.min(found.x, r.left - box.left);
				found.right = Math.max(found.right, r.right - box.left);
			} else {
				const h = Math.max(line, r.height);
				bands.set(key, {
					x: r.left - box.left,
					right: r.right - box.left,
					y: r.top - box.top - (h - r.height) / 2,
					h
				});
			}
		}
		selRects = [...bands.values()].map((b) => ({ x: b.x, y: b.y, w: b.right - b.x, h: b.h }));
	});

	$effect(() => {
		void value;
		void caret;
		if (!marker || !wrapper) return;
		const m = marker.getBoundingClientRect();
		const w = wrapper.getBoundingClientRect();
		caretPos = { x: m.left - w.left, y: m.top - w.top };
		caretScreen = { x: m.left, y: m.top };
	});

	// Reset the highlight whenever the trigger moves or its query changes.
	let lastKey = '';
	$effect(() => {
		const key = `${value}:${caret}`;
		if (key === lastKey) return;
		lastKey = key;
		suggestIdx = 0;
	});

	const caretCss = $derived(
		caretPos
			? Object.entries(caretStyle(caretPos, blinking))
					.map(([k, v]) => `${k.replace(/[A-Z]/g, (c) => `-${c.toLowerCase()}`)}:${v}`)
					.join(';')
			: ''
	);

	function onKeyDown(e: KeyboardEvent) {
		pauseBlink();
		const result = handleKey(
			barState,
			vocab,
			{ key: e.key, shiftKey: e.shiftKey, isComposing: e.isComposing, keyCode: e.keyCode }
		);
		if (result.prevented) e.preventDefault();
		if (result.state !== barState) applyState(result.state);
		if (result.forwarded) onkeydown?.(e);
		requestAnimationFrame(syncCaret);
	}

	function onPick(domIndex: number) {
		// The panel is in DOM order; the ranked list is best-first.
		const ranked = rankedSuggestions(barState, vocab);
		const term = ranked[ranked.length - 1 - domIndex];
		if (term) applyState(acceptSuggestion(barState, term));
	}

	async function onInput() {
		await tick();
		requestAnimationFrame(syncCaret);
		pauseBlink();
	}
</script>

<div bind:this={wrapper} class="relative w-full">
	<!-- The selection, under the words rather than over them. First in the DOM
	     so it paints below the overlay: the tokens keep their colours through a
	     highlight, which is the whole reason there is an overlay. -->
	<div aria-hidden="true" class="pointer-events-none absolute inset-0">
		{#each selRects as r, i (i)}
			<span
				class="smooth-select absolute"
				style="left:{r.x}px;top:{r.y}px;width:{r.w}px;height:{r.h}px"
			></span>
		{/each}
	</div>

	<!-- Coloured overlay. Also carries the marker the caret is measured from,
	     so it must lay text out identically to the textarea below it. -->
	<div
		bind:this={overlay}
		aria-hidden="true"
		class="smooth-layout pointer-events-none absolute inset-0"
	>
		{#each bar.overlay as seg, i (i)}{#if seg.role === 'marker'}<span bind:this={marker}
					>&#8203;</span
				>{:else}<span
					style="{seg.color
						? `color:${toRamp(seg.color)};${seg.role === 'token' ? 'font-weight:700;' : ''}`
						: ''}{seg.animation ? `animation:${seg.animation}` : ''}">{seg.text}</span
				>{/if}{/each}
	</div>

	<!-- No focus ring on this one: its focus is shown by the caret it draws
	     itself. The rule is in `app.css` beside the ring it excepts, and not a
	     `focus:outline-none` here, because a Tailwind utility is layered and the
	     ring is not — the class sat here for months looking like it worked while
	     the ring was drawn on every tap and clipped into a red line above the
	     notch. -->
	<textarea
		bind:this={ta}
		bind:value
		{placeholder}
		rows="1"
		spellcheck="false"
		autocomplete="off"
		autocapitalize="none"
		{...{ autocorrect: 'off' }}
		class="smooth-layout relative w-full resize-none bg-transparent"
		style="color:transparent;caret-color:transparent;background:transparent"
		oninput={onInput}
		onkeydown={onKeyDown}
		onkeyup={syncCaret}
		onclick={syncCaret}
		onselect={syncCaret}
		onpaste={(e) => onpaste?.(e)}
		onfocus={() => {
			focused = true;
			syncCaret();
			onfocus?.();
		}}
		onblur={() => {
			focused = false;
			onblur?.();
		}}
	></textarea>

	<!-- The caret. 80ms linear, and it stops blinking while you type. -->
	{#if caretPos}
		<div class="pointer-events-none absolute" style="left:0;top:0;{caretCss}"></div>
	{/if}
</div>

{#if bar.suggestOpen && caretScreen}
	<!-- Fixed rather than absolute so the capture box's overflow cannot clip
	     it — the source portals this to <body> for the same reason.

	     The list is rendered in the order `view()` gives it, which puts the
	     best match at the BOTTOM, nearest the caret on desktop and nearest the
	     thumb on mobile. Inverted on purpose, and the arrow keys are inverted
	     to match; re-sorting this list silently breaks them. -->
	<div
		class="trophic-scrollbar-hide fixed z-50 max-h-[180px] w-fit overflow-y-auto bg-surface py-1 shadow-lg"
		style="left:{Math.max(8, caretScreen.x - 8)}px;top:{caretScreen.y}px;
		       transform:translateY(-100%) translateY(-6px)"
	>
		{#each bar.suggestions as s, i (i)}
			<button
				type="button"
				class="block w-full whitespace-nowrap px-3 py-1 text-left font-mono text-[12px] transition-colors {s.selected
					? 'bg-neutral-200'
					: ''}"
				style="color:{toRamp(s.color)}"
				onmousedown={(e) => {
					e.preventDefault();
					onPick(i);
				}}
			>
				{s.label}
			</button>
		{/each}
	</div>
{/if}

<style>
	/* Shared text layout: the overlay and the textarea must agree glyph for
	   glyph, or the measured caret drifts as a line fills up. Every property
	   here is on *both* layers for that reason, including the ones that look
	   cosmetic — `letter-spacing` especially, which produces a drift small
	   enough to argue about and large enough to see.

	   The draft is 22px rather than the 18px everything else reads at, which is
	   what gives the bar its weight: the thought is the largest thing on the
	   screen while it is being written. It was briefly set in Archivo, on the
	   argument that a draft should read as prose; the phosphor re-light took
	   that back, because a monitor sets everything in one face and a second
	   one reads as a different program. */
	.smooth-layout {
		font-family: var(--font-sans);
		font-size: 22px;
		line-height: 32px;
		letter-spacing: -0.012em;
		/* There is no card around this any more, so the draft is flush with the
		   left edge of the column and lines up with the notched indicator under
		   it and everything else the screen stacks. The padding that remains is
		   doing two jobs and no decorative one: the right side is the reserve
		   the paperclip sits in, and the top and bottom keep the caret and the
		   descenders off the line. Both layers carry it, so the overlay, the
		   textarea and the caret all measure from the same origin. */
		padding: 10px 44px 14px 0;
		margin: 0;
		border: 0;
		box-sizing: border-box;
		white-space: pre-wrap;
		overflow-wrap: break-word;
		word-break: normal;
		tab-size: 4;
		color: var(--color-ink);
	}

	textarea::placeholder {
		color: var(--color-neutral-600);
	}

	/* The native selection is switched off, the same way and for the same reason
	   as the native caret above it: what would be painted is the *textarea*,
	   which sits over the overlay and whose glyphs are transparent, so the
	   browser's highlight is a block that covers the words it is highlighting.
	   Tinting it does not fix that on WebKit — see `selRects`, which is the
	   highlight this draws instead. */
	textarea::selection {
		background: transparent;
		color: transparent;
		-webkit-text-fill-color: transparent;
	}

	/* And the drawn one. Dark enough to read lit type on, because the type is
	   on top of it and keeps its own colour — this is the one selection in the
	   app that is not inverse video, and that is the trade: the tokens stay
	   legible as tokens while you drag across them. */
	.smooth-select {
		background: var(--color-accent-300);
	}
</style>
