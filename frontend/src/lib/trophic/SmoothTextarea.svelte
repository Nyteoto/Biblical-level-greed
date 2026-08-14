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
	 * Blinking stops while you type and resumes 530ms after the last keystroke:
	 * a caret that blinks mid-word reads as an idle terminal.
	 */
	import { tick } from 'svelte';
	import { tokenize, activeTrigger, type Token } from './tokenize';
	import { buildTrie, scoredSearch, loadStats, saveStats, recordUse, type UsageStats } from './trie';
	import { SYNTAX_COLORS, UI_COLORS } from './colors';
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
	let caretPos = $state<{ x: number; y: number } | null>(null);
	let caretScreen = $state<{ x: number; y: number } | null>(null);
	let blinking = $state(true);
	let suggestIdx = $state(0);
	let blinkTimer: ReturnType<typeof setTimeout>;

	function pauseBlink() {
		blinking = false;
		clearTimeout(blinkTimer);
		blinkTimer = setTimeout(() => (blinking = true), 530);
	}

	export function focus() {
		ta?.focus();
	}

	export function insertText(text: string) {
		if (!ta) return;
		ta.focus();
		const start = ta.selectionStart;
		const end = ta.selectionEnd;
		const next = value.slice(0, start) + text + value.slice(end);
		const nextCaret = start + text.length;
		value = next;
		requestAnimationFrame(() => {
			ta?.setSelectionRange(nextCaret, nextCaret);
			caret = nextCaret;
		});
	}

	function syncCaret() {
		if (ta) caret = ta.selectionStart ?? 0;
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

	// ── Colouring ──────────────────────────────────────────────────────────

	const tokens = $derived(tokenize(value));

	function colorForTag(tagLower: string): string {
		const fid = vocab?.tag_to_folder?.[tagLower];
		const folder = vocab?.folders?.find((f) => f.id === fid);
		// Dim for a tag no folder has claimed — the source appends "99" alpha.
		return folder?.color ?? SYNTAX_COLORS.folder + '99';
	}

	function tokenColor(t: Token): string | undefined {
		switch (t.kind) {
			case 'folder':
				return colorForTag(t.value);
			case 'time':
				return SYNTAX_COLORS.time;
			case 'pattern':
				return SYNTAX_COLORS.pattern;
			case 'directive':
				return SYNTAX_COLORS.directive;
			case 'todo':
				return SYNTAX_COLORS.todo;
			default:
				return undefined;
		}
	}

	type Seg = { text: string; color?: string; blink: boolean; marker?: boolean };

	/** The overlay, with the caret marker split into the token it falls in. */
	const segments = $derived.by(() => {
		const blinkSet = new Set(blinkIndices);
		const out: Seg[] = [];
		let placed = false;
		for (let ti = 0; ti < tokens.length; ti++) {
			const t = tokens[ti];
			const blink = blinkSet.has(ti);
			const color = blink ? undefined : tokenColor(t);
			if (!placed && caret >= t.start && caret <= t.end) {
				const cut = caret - t.start;
				out.push({ text: t.raw.slice(0, cut), color, blink });
				out.push({ text: '​', blink: false, marker: true });
				out.push({ text: t.raw.slice(cut), color, blink });
				placed = true;
			} else {
				out.push({ text: t.raw, color, blink });
			}
		}
		if (!placed) out.push({ text: '​', blink: false, marker: true });
		return out;
	});

	// ── Autocomplete ───────────────────────────────────────────────────────

	let stats = $state<UsageStats>({});
	$effect(() => {
		stats = loadStats();
	});

	const folderNames = $derived(
		(vocab?.folders ?? []).map((f) => f.name).filter((n) => typeof n === 'string' && n.length > 0)
	);
	const tries = $derived(
		vocab
			? {
					tags: buildTrie(vocab.tags),
					times: buildTrie(vocab.times),
					patterns: buildTrie(vocab.patterns),
					folders: buildTrie(folderNames)
				}
			: null
	);

	const trigger = $derived(activeTrigger(value, caret));

	const suggestions = $derived.by(() => {
		if (!trigger || !tries || !vocab) return [] as string[];
		if (trigger.char === '-') return scoredSearch(tries.folders, folderNames, trigger.query, stats);
		if (trigger.char === '<') return scoredSearch(tries.tags, vocab.tags, trigger.query, stats);
		if (trigger.char === '{') return scoredSearch(tries.times, vocab.times, trigger.query, stats);
		return scoredSearch(tries.patterns, vocab.patterns, trigger.query, stats);
	});
	const showSuggest = $derived(!!trigger && suggestions.length > 0);

	// Reset the highlight whenever the trigger moves or its query changes.
	let lastTriggerKey = '';
	$effect(() => {
		const key = trigger ? `${trigger.start}:${trigger.query}` : '';
		if (key !== lastTriggerKey) {
			lastTriggerKey = key;
			suggestIdx = 0;
		}
	});

	/** The remainder the user has not typed yet, shown inline IDE-style. */
	const ghostText = $derived.by(() => {
		if (!showSuggest || !trigger) return '';
		const sugg = suggestions[suggestIdx];
		if (!sugg) return '';
		const q = trigger.query.toLowerCase();
		const idx = sugg.toLowerCase().indexOf(q);
		const remainder = idx >= 0 ? sugg.slice(idx + q.length) : sugg;
		if (!remainder) return '';
		if (trigger.char === '<') return remainder + '>';
		if (trigger.char === '{') return remainder + '}';
		return remainder;
	});

	function suggestionColor(s: string): string {
		if (trigger?.char === '<') return colorForTag(s);
		if (trigger?.char === '{') return SYNTAX_COLORS.time;
		if (trigger?.char === '-') return SYNTAX_COLORS.directive;
		return SYNTAX_COLORS.pattern;
	}

	function suggestionLabel(s: string): string {
		if (trigger?.char === '<') return `<${s}>`;
		if (trigger?.char === '{') return `{${s}}`;
		if (trigger?.char === '-') return `--${s}`;
		return `\\${s}`;
	}

	function applySuggestion(sugg: string) {
		if (!trigger) return;
		let before: string;
		let insert: string;
		if (trigger.char === '-') {
			before = value.slice(0, trigger.start);
			// Quote anything the unquoted --directive regex could not read back.
			const needsQuote = /[^\p{L}\p{N}\p{M}_-]/u.test(sugg);
			insert = needsQuote ? `--"${sugg}" ` : `--${sugg} `;
		} else {
			before = value.slice(0, trigger.start + 1); // keep the trigger char
			if (trigger.char === '<') insert = `${sugg}> `;
			else if (trigger.char === '{') insert = `${sugg}} `;
			else insert = `${sugg} `;
		}
		const after = value.slice(caret);
		const nextCaret = before.length + insert.length;
		stats = recordUse(stats, sugg);
		saveStats(stats);
		value = before + insert + after;
		requestAnimationFrame(() => {
			if (!ta) return;
			ta.focus();
			ta.setSelectionRange(nextCaret, nextCaret);
			caret = nextCaret;
		});
	}

	function handleKeyDown(e: KeyboardEvent) {
		pauseBlink();
		// While an IME is composing (Vietnamese Telex, Japanese, Korean,
		// Chinese…) Enter/Space/Arrows belong to the IME — hijacking them
		// commits the wrong thing or cuts the composed character short.
		if (e.isComposing || e.keyCode === 229) {
			requestAnimationFrame(syncCaret);
			return;
		}
		if (showSuggest) {
			// The panel renders most-relevant at the BOTTOM, nearest the caret
			// and the thumb, so visual "down" is a lower array index. The arrow
			// effects are swapped so ArrowDown still moves the highlight down.
			if (e.key === 'ArrowDown') {
				e.preventDefault();
				suggestIdx = (suggestIdx - 1 + suggestions.length) % suggestions.length;
				return;
			}
			if (e.key === 'ArrowUp') {
				e.preventDefault();
				suggestIdx = (suggestIdx + 1) % suggestions.length;
				return;
			}
			if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
				e.preventDefault();
				applySuggestion(suggestions[suggestIdx]);
				return;
			}
			if (e.key === 'Escape') {
				e.preventDefault();
				return;
			}
		}
		onkeydown?.(e);
		requestAnimationFrame(syncCaret);
	}

	async function handleInput() {
		await tick();
		requestAnimationFrame(syncCaret);
		pauseBlink();
	}
</script>

<div bind:this={wrapper} class="relative w-full">
	<!-- Coloured overlay. Also carries the marker the caret is measured from,
	     so it must lay text out identically to the textarea below it. -->
	<div aria-hidden="true" class="smooth-layout pointer-events-none absolute inset-0">
		{#each segments as seg, i (i)}
			{#if seg.marker}
				<span bind:this={marker}>{seg.text}</span>{#if ghostText}<span class="ghost"
						>{ghostText}</span
					>{/if}
			{:else}
				<span
					class={seg.blink ? 'blink-token' : ''}
					style={seg.color ? `color:${seg.color}` : undefined}>{seg.text}</span
				>
			{/if}
		{/each}
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
		oninput={handleInput}
		onkeydown={handleKeyDown}
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
		<div
			class="pointer-events-none absolute"
			style="left:0;top:0;width:2px;height:1.4em;background:{UI_COLORS.ink};
			       box-shadow:0 0 6px rgba(231,229,228,0.25);
			       transform:translate({caretPos.x}px,{caretPos.y}px);
			       transition:transform 80ms linear;
			       animation:{blinking ? 'caret-blink 1s ease-in-out infinite' : 'none'}"
		></div>
	{/if}
</div>

{#if showSuggest && caretScreen}
	<!-- Fixed rather than absolute so the capture box's overflow cannot clip
	     it — the source portals this to <body> for the same reason. -->
	<div
		class="trophic-scrollbar-hide fixed z-50 max-h-[180px] w-fit overflow-y-auto rounded-sm border border-stone-700/70 bg-[#1b1613] py-1 shadow-lg shadow-black/40"
		style="left:{Math.max(8, caretScreen.x - 8)}px;top:{caretScreen.y}px;
		       transform:translateY(-100%) translateY(-6px)"
	>
		<!-- Reversed: index 0 is the best match and sits at the visual bottom,
		     nearest the caret on desktop and the thumb on mobile. Inverted on
		     purpose — standard dropdowns put the best match at the top. -->
		{#each suggestions as _, ri (ri)}
			{@const i = suggestions.length - 1 - ri}
			{@const s = suggestions[i]}
			<button
				type="button"
				class="block w-full whitespace-nowrap px-3 py-1 text-left font-mono text-[12px] transition-colors {i ===
				suggestIdx
					? 'bg-stone-800/80'
					: ''}"
				style="color:{suggestionColor(s)}"
				onmousedown={(e) => {
					e.preventDefault();
					applySuggestion(s);
				}}
				onmouseenter={() => (suggestIdx = i)}
			>
				{suggestionLabel(s)}
			</button>
		{/each}
	</div>
{/if}

<style>
	/* Shared text layout: the overlay and the textarea must agree glyph for
	   glyph, or the measured caret drifts as a line fills up. */
	.smooth-layout {
		font-family: var(--font-mono);
		font-size: 18px;
		line-height: 28px;
		padding: 12px 40px 12px 0;
		margin: 0;
		border: 0;
		box-sizing: border-box;
		white-space: pre-wrap;
		overflow-wrap: break-word;
		word-break: normal;
		letter-spacing: normal;
		tab-size: 4;
		color: #e7e5e4;
	}

	.ghost {
		color: #78716c;
	}

	.blink-token {
		color: #ef4444;
		animation: onboard-blink 0.6s ease-in-out infinite;
	}

	textarea::placeholder {
		color: #57534e;
	}
</style>
