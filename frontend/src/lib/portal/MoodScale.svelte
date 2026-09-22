<script lang="ts">
	/**
	 * One to ten, drawn as ten cells. Selection is inversion — a white cell with
	 * the ground cut out of it — on the screen as on the print.
	 *
	 * Read-only unless `onpick` is given; the sealed Record draws the same row.
	 */
	let {
		value,
		onpick
	}: {
		value: number | null;
		onpick?: (n: number) => void;
	} = $props();
</script>

<div class="flex max-w-[520px]" role={onpick ? 'radiogroup' : undefined}>
	{#each { length: 10 } as _, i (i)}
		{@const n = i + 1}
		{#if onpick}
			<button
				type="button"
				role="radio"
				aria-checked={value === n}
				class="h-11 min-w-0 flex-1 text-[14px] font-bold tabular-nums transition-colors {value === n
					? 'accent-fill'
					: 'text-neutral-700 hover:text-ink'}"
				style="box-shadow: inset 0 0 0 1px var(--color-neutral-400)"
				onclick={() => onpick(n)}>{n}</button
			>
		{:else}
			<span
				class="flex h-9 min-w-0 flex-1 items-center justify-center text-[13px] tabular-nums {value === n
					? 'accent-fill font-extrabold'
					: 'text-neutral-600'}"
				style="box-shadow: inset 0 0 0 1px var(--color-neutral-400)">{n}</span
			>
		{/if}
	{/each}
</div>
