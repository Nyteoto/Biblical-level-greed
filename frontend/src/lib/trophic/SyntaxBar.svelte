<script lang="ts">
	/** Mobile syntax keys. Ported from SyntaxBar.tsx.
	 *
	 * `<`, `{`, `\` and `--` are all buried two taps deep on a phone keyboard,
	 * which is enough friction to stop someone tagging a thought at all. Split
	 * left and right so both thumbs reach a group. */
	import { SYNTAX_COLORS } from './colors';

	let { visible, oninsert }: { visible: boolean; oninsert: (text: string) => void } = $props();

	const LEFT = [
		{ label: '<', color: SYNTAX_COLORS.folder },
		{ label: '>', color: SYNTAX_COLORS.folder },
		{ label: '{', color: SYNTAX_COLORS.time }
	];
	const RIGHT = [
		{ label: '}', color: SYNTAX_COLORS.time },
		{ label: '\\', color: SYNTAX_COLORS.pattern },
		{ label: '--', color: SYNTAX_COLORS.directive }
	];

	let pressed = $state<string | null>(null);
</script>

{#if visible}
	<div class="flex justify-between pt-2">
		{#each [LEFT, RIGHT] as group, gi (gi)}
			<div class="flex gap-1.5">
				{#each group as k (k.label)}
					<button
						type="button"
						class="min-w-[40px] rounded-lg border py-1.5 text-center text-[14px] leading-none font-semibold transition-[transform,background,box-shadow] duration-75 select-none"
						style="color:{pressed === k.label ? '#14100c' : k.color};
						       background:{pressed === k.label ? '#57534e' : '#241d18'};
						       border-color:{pressed === k.label ? '#78716c' : '#3a322a'};
						       box-shadow:{pressed === k.label ? 'none' : '0 1px 0 0 #3a322a'};
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
{/if}
