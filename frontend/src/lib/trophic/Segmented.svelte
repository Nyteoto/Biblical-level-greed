<script lang="ts" generics="T extends string">
	/**
	 * A row of two or three exclusive choices, on a tinted track.
	 *
	 * There were two of these written out by hand — the Log's `Opens on` in
	 * Settings and a folder's lifecycle behind its name — and they had already
	 * drifted apart at the gap between segments. Neither is more canonical than
	 * the other, so the shape lives here now and both call it.
	 *
	 * The active segment is a white surface with `--shadow-sm` rather than the
	 * accent gradient: this control picks between things that are all equally
	 * ordinary, and the accent is reserved for the one live thing on a screen.
	 */
	let {
		options,
		value,
		onpick,
		label
	}: {
		options: { value: T; label: string }[];
		value: T;
		onpick: (value: T) => void;
		/** Names the group for a screen reader; the segments are its buttons. */
		label?: string;
	} = $props();
</script>

<span class="flex gap-[3px] rounded-[9px] bg-neutral-200 p-[3px]" role="group" aria-label={label}>
	{#each options as option (option.value)}
		<button
			type="button"
			aria-pressed={value === option.value}
			class="rounded-[7px] px-2.5 py-[5px] text-[12px] transition-colors {value === option.value
				? 'bg-surface font-bold shadow-sm'
				: 'font-semibold text-neutral-700 hover:text-ink'}"
			onclick={() => onpick(option.value)}
		>
			{option.label}
		</button>
	{/each}
</span>
