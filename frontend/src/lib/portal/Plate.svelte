<script lang="ts">
	/**
	 * A plate: one photograph or clip, mounted on the record sheet by its four
	 * corners and captioned underneath with its number.
	 *
	 * The corners are the design canvas's mounting marks, drawn with inset
	 * shadows rather than borders so they cost nothing to composite. The plate
	 * holds whatever it is given — an image, a video, an empty slot — and says
	 * nothing about what that is; the sheet decides.
	 */
	import type { Snippet } from 'svelte';

	let {
		large = false,
		children,
		caption
	}: {
		/** The first plate is mounted large, the rest two to a row. */
		large?: boolean;
		children: Snippet;
		caption?: Snippet;
	} = $props();

	const mark = $derived(large ? 16 : 12);
</script>

<figure class="m-0 flex min-w-0 flex-col gap-[7px]">
	<div
		class="relative {large ? 'h-[196px] p-2' : 'h-[112px] p-[7px]'}"
		style="box-shadow: inset 0 0 0 1px var(--color-neutral-400)"
	>
		<div class="h-full w-full overflow-hidden">
			{@render children()}
		</div>
		{#each [['left', 'top', '2px 2px'], ['right', 'top', '-2px 2px'], ['left', 'bottom', '2px -2px'], ['right', 'bottom', '-2px -2px']] as [x, y, inset] (x + y)}
			<span
				aria-hidden="true"
				class="pointer-events-none absolute"
				style="{x}: 3px; {y}: 3px; width: {mark}px; height: {mark}px; box-shadow: inset {inset} 0 0 var(--color-neutral-700)"
			></span>
		{/each}
	</div>
	{#if caption}
		<figcaption
			class="flex min-w-0 items-baseline gap-3 text-[10px] tracking-[0.14em] text-neutral-600 uppercase tabular-nums"
		>
			{@render caption()}
		</figcaption>
	{/if}
</figure>
