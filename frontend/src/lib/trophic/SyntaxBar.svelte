<script lang="ts">
	/** The syntax keys. Ported from SyntaxBar.tsx.
	 *
	 * `<`, `{`, `\` and `--` are all buried two taps deep on a phone keyboard,
	 * which is enough friction to stop someone tagging a thought at all.
	 *
	 * **Five keys, one per mark, in one group.** The source split seven keys
	 * left and right so both thumbs reached a group, and the split fell
	 * between `{` and `}` — the two halves of one mark on opposite sides of the
	 * screen, with the gap for the notch between them. A bracket is one thing
	 * to type, so it is one key: `<>` and `{}` put down both halves and leave
	 * the caret between them, or wrap whatever is selected. Grouped at the
	 * right, where the thumb that is not holding the device is.
	 *
	 * They are on every device now, not just a touch one. The screen this app
	 * is actually read and written on is an iPad in landscape with no hardware
	 * keyboard, which the device classification calls a tablet rather than a
	 * mobile — and on that machine the row was never drawn. Showing it always
	 * costs a desktop one line of chrome it can ignore, which is the cheaper
	 * mistake of the two.
	 *
	 * Each glyph is painted in the colour of what it makes, so the row doubles
	 * as the legend for the syntax. That is why there is no separate key.
	 */
	import { SYNTAX_COLORS } from './colors';

	let { oninsert }: { oninsert: (text: string, close?: string) => void } = $props();

	// `@` sits next to `\` because they are the same kind of key: a bare word
	// that tags the line and points at nothing.
	const KEYS = [
		{ label: '<>', open: '<', close: '>', color: SYNTAX_COLORS.folder },
		{ label: '{}', open: '{', close: '}', color: SYNTAX_COLORS.time },
		{ label: '\\', open: '\\', close: '', color: SYNTAX_COLORS.pattern },
		{ label: '@', open: '@', close: '', color: SYNTAX_COLORS.place },
		{ label: '--', open: '--', close: '', color: SYNTAX_COLORS.directive }
	];

	let pressed = $state<string | null>(null);
</script>

<!-- Five 50px keys and their gaps are ~282px, which a phone's column holds
     with a little to spare; it still wraps rather than running off the edge
     if one does not. -->
<div class="flex flex-wrap justify-end gap-2">
	{#each KEYS as k (k.label)}
		<button
			type="button"
			class="min-w-[50px] py-[10px] text-center text-[16px] leading-none font-bold tracking-[0.04em] transition-[transform,background,box-shadow] duration-75 select-none"
			style="color:{k.color};
			       background:{pressed === k.label ? 'var(--color-neutral-200)' : 'var(--color-surface)'};
			       box-shadow:{pressed === k.label ? 'none' : 'var(--shadow-sm)'};
			       transform:translateY({pressed === k.label ? 1 : 0}px);
			       -webkit-tap-highlight-color:transparent;touch-action:manipulation"
			onmousedown={(e) => {
				e.preventDefault();
				pressed = k.label;
			}}
			onmouseup={() => {
				pressed = null;
				oninsert(k.open, k.close);
			}}
			onmouseleave={() => (pressed = null)}
			ontouchstart={(e) => {
				e.preventDefault();
				pressed = k.label;
			}}
			ontouchend={(e) => {
				e.preventDefault();
				pressed = null;
				oninsert(k.open, k.close);
			}}
			ontouchcancel={() => (pressed = null)}
		>
			{k.label}
		</button>
	{/each}
</div>
