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
	let marker = $state<HTMLSpanElement | null>(null);

	let caret = $state(0);
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

	export function insertText(text: string) {
		if (!ta) return;
		ta.focus();
		const start = ta.selectionStart;
		const end = ta.selectionEnd;
		const nextCaret = start + text.length;
		value = value.slice(0, start) + text + value.slice(end);
		requestAnimationFrame(() => {
			ta?.setSelectionRange(nextCaret, nextCaret);
			caret = nextCaret;
		});
	}

	function syncCaret() {
		if (ta) caret = ta.selectionStart ?? 0;
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
			caret = next.caret;
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
	<!-- Coloured overlay. Also carries the marker the caret is measured from,
	     so it must lay text out identically to the textarea below it. -->
	<div aria-hidden="true" class="smooth-layout pointer-events-none absolute inset-0">
		{#each bar.overlay as seg, i (i)}{#if seg.role === 'marker'}<span bind:this={marker}
					>&#8203;</span
				>{:else}<span
					style="{seg.color ? `color:${seg.color};` : ''}{seg.animation
						? `animation:${seg.animation}`
						: ''}">{seg.text}</span
				>{/if}{/each}
	</div>

	<textarea
		bind:this={ta}
		bind:value
		{placeholder}
		rows="1"
		spellcheck="false"
		autocomplete="off"
		autocapitalize="none"
		{...{ autocorrect: 'off' }}
		class="smooth-layout relative w-full resize-none bg-transparent focus:outline-none"
		style="color:transparent;caret-color:transparent;background:transparent"
		oninput={onInput}
		onkeydown={onKeyDown}
		onkeyup={syncCaret}
		onclick={syncCaret}
		onselect={syncCaret}
		onpaste={(e) => onpaste?.(e)}
		onfocus={() => {
			syncCaret();
			onfocus?.();
		}}
		onblur={() => onblur?.()}
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
		class="trophic-scrollbar-hide fixed z-50 max-h-[180px] w-fit overflow-y-auto rounded-[10px] bg-surface py-1 shadow-lg"
		style="left:{Math.max(8, caretScreen.x - 8)}px;top:{caretScreen.y}px;
		       transform:translateY(-100%) translateY(-6px)"
	>
		{#each bar.suggestions as s, i (i)}
			<button
				type="button"
				class="block w-full whitespace-nowrap px-3 py-1 text-left font-mono text-[12px] transition-colors {s.selected
					? 'bg-neutral-200'
					: ''}"
				style="color:{s.color}"
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

	   The draft is Archivo at 22px rather than a mono at 18px. That is the
	   redesign's largest single change to how the bar feels: the thought reads
	   as prose while it is being written, and the mono is kept for the things
	   that are actually machine-shaped — timestamps, file names, paths and the
	   syntax keys. */
	.smooth-layout {
		font-family: var(--font-sans);
		font-size: 22px;
		line-height: 32px;
		letter-spacing: -0.012em;
		/* These are the writing card's padding, not the textarea's: the card
		   has none of its own, so that the overlay, the textarea and the caret
		   all measure from the same origin. The right side is the reserve the
		   paperclip sits in. */
		padding: 24px 52px 18px 22px;
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
</style>
