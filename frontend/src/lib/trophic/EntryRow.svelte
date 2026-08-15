<script lang="ts">
	/** One line in the log. Ported from EntryRow.tsx.
	 *
	 * The stagger (`index * 50ms`) on a 400ms `entry-fade-in` is what makes a
	 * day's entries cascade in from the left rather than all appear at once. */
	import ColorizedText from './ColorizedText.svelte';
	import EntryMedia from './EntryMedia.svelte';
	import TodoEntryText from './TodoEntryText.svelte';
	import type { Entry } from './api';

	let {
		entry,
		index = 0,
		ontoggle
	}: { entry: Entry; index?: number; ontoggle?: (line: number) => void } = $props();

	const time = $derived(
		new Date(entry.ts).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
	);
</script>

<div
	data-entry-id={entry.id}
	class="flex min-w-0 items-start gap-3"
	style="animation:entry-fade-in 400ms ease-out both;animation-delay:{index * 50}ms"
>
	<span class="w-10 shrink-0 pt-0.5 text-right text-[10px] text-stone-500">{time}</span>
	<div class="min-w-0 flex-1">
		{#if entry.todo_lines.length > 0}
			<TodoEntryText {entry} {ontoggle} />
		{:else if entry.clean_text}
			<span
				class="block font-mono text-[13px] leading-relaxed whitespace-pre-wrap text-stone-300"
				style="overflow-wrap:anywhere;word-break:break-word"
			>
				<ColorizedText text={entry.clean_text} />
			</span>
		{/if}
		<EntryMedia refs={entry.media ?? []} />
	</div>
</div>
