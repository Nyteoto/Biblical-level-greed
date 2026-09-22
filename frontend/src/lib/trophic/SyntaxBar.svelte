<script lang="ts">
	/** The syntax keys. Ported from SyntaxBar.tsx.
	 *
	 * `<`, `{`, `\` and `--` are all buried two taps deep on a phone keyboard,
	 * which is enough friction to stop someone tagging a thought at all. Split
	 * left and right so both thumbs reach a group.
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

	let { oninsert }: { oninsert: (text: string) => void } = $props();

	const LEFT = [
		{ label: '<', color: SYNTAX_COLORS.folder },
		{ label: '>', color: SYNTAX_COLORS.folder },
		{ label: '{', color: SYNTAX_COLORS.time }
	];
	// `@` sits next to `\` because they are the same kind of key: a bare word
	// that tags the line and points at nothing. That leaves the right group one
	// wider than the left, which is the right trade — the split is about which
	// thumb can reach a group, not about the two being the same size.
	const RIGHT = [
		{ label: '}', color: SYNTAX_COLORS.time },
		{ label: '\\', color: SYNTAX_COLORS.pattern },
		{ label: '@', color: SYNTAX_COLORS.place },
		{ label: '--', color: SYNTAX_COLORS.directive }
	];

	let pressed = $state<string | null>(null);
</script>

<!-- Wraps, because seven 46px keys and their gaps need ~362px and a phone
     gives this column about 266. Unwrapped, `\` and `@` were off the right
     edge with nothing to scroll — two of the five marks unreachable on the
     device the row exists for. Above that width nothing moves. -->
<div class="flex flex-wrap justify-between gap-2">
	{#each [LEFT, RIGHT] as group, gi (gi)}
		<div class="flex gap-2">
			{#each group as k (k.label)}
				<button
					type="button"
					class="min-w-[46px] rounded-[11px] py-[10px] text-center text-[16px] leading-none font-bold transition-[transform,background,box-shadow] duration-75 select-none"
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
						oninsert(k.label);
					}}
					onmouseleave={() => (pressed = null)}
					ontouchstart={(e) => {
						e.preventDefault();
						pressed = k.label;
					}}
					ontouchend={(e) => {
						e.preventDefault();
						pressed = null;
						oninsert(k.label);
					}}
					ontouchcancel={() => (pressed = null)}
				>
					{k.label}
				</button>
			{/each}
		</div>
	{/each}
</div>
