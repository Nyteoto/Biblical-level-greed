<script lang="ts" generics="T extends string">
	/**
	 * A row of two or three exclusive choices, on a tinted track.
	 *
	 * There were two of these written out by hand — the Log's `Opens on` in
	 * Settings and a folder's lifecycle behind its name — and they had already
	 * drifted apart at the gap between segments. Neither is more canonical than
	 * the other, so the shape lives here now and both call it.
	 *
	 * **The active segment is the accent fill**, the same inversion the rail,
	 * the folder picker and the year list use. It was a raised surface with a
	 * shadow on the grounds that these choices are ordinary — but the chosen
	 * one *is* the current thing, which is what white means in this app, and a
	 * fourth way of drawing "selected" was a fourth thing to learn.
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

<span class="flex gap-[3px] bg-neutral-200 p-[3px]" role="group" aria-label={label}>
	{#each options as option (option.value)}
		<button
			type="button"
			aria-pressed={value === option.value}
			class="px-2.5 py-[5px] text-[12px] transition-colors {value === option.value
				? 'accent-fill font-bold'
				: 'font-semibold text-neutral-700 hover:text-ink'}"
			onclick={() => onpick(option.value)}
		>
			{option.label}
		</button>
	{/each}
</span>
