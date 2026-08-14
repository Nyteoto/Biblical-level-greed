<script lang="ts">
	/** An entry that has `--todo` lines. Ported from TodoEntryText.tsx.
	 *
	 * `todo_lines` and `todo_done` are line *indices* into the entry's text —
	 * which is safe here precisely because the text is immutable: the log is
	 * append-only, so line 2 is line 2 forever. Ticking appends a `check`
	 * event and deletes nothing. */
	import ColorizedText from './ColorizedText.svelte';
	import { UI_COLORS } from './colors';
	import type { Entry } from './api';

	let { entry, ontoggle }: { entry: Entry; ontoggle?: (line: number) => void } = $props();

	const lines = $derived(entry.clean_text.split('\n'));
	const done = $derived(new Set(entry.todo_done));
</script>

<div class="flex min-w-0 flex-1 flex-col gap-0.5">
	{#each lines as line, li (li)}
		<div class="flex items-start gap-2">
			{#if entry.todo_lines.includes(li)}
				<button
					type="button"
					aria-label={done.has(li) ? 'untick' : 'tick'}
					class="mt-[3px] flex h-[14px] w-[14px] shrink-0 items-center justify-center rounded border border-stone-600 transition-colors hover:border-stone-400"
					style={done.has(li)
						? `background-color:${UI_COLORS.muted};border-color:${UI_COLORS.muted}`
						: undefined}
					onclick={(e) => {
						e.stopPropagation();
						ontoggle?.(li);
					}}
				>
					{#if done.has(li)}
						<svg
							width="10"
							height="10"
							viewBox="0 0 10 10"
							fill="none"
							stroke="#e7e5e4"
							stroke-width="1.5"
							stroke-linecap="round"
							stroke-linejoin="round"
						>
							<path d="M2 5.5 L4 7.5 L8 3" />
						</svg>
					{/if}
				</button>
			{/if}
			<span
				class="font-mono text-[13px] leading-relaxed {done.has(li)
					? 'text-stone-500 line-through'
					: 'text-stone-300'}"
				style="overflow-wrap:anywhere;word-break:break-word"
			>
				<ColorizedText text={line} />
			</span>
		</div>
	{/each}
</div>
