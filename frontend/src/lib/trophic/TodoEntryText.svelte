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
					class="mt-[5px] flex h-[15px] w-[15px] shrink-0 items-center justify-center rounded-[5px] border transition-colors"
					style={done.has(li)
						? `background-color:${UI_COLORS.dim};border-color:${UI_COLORS.dim}`
						: `border-color:${UI_COLORS.muted}`}
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
							stroke="#ffffff"
							stroke-width="1.5"
							stroke-linecap="round"
							stroke-linejoin="round"
						>
							<path d="M2 5.5 L4 7.5 L8 3" />
						</svg>
					{/if}
				</button>
			{/if}
			<!-- The type is inherited from the row this sits in — the lead day sets
			     17px and a light row sets 16px, and a todo is a line like any
			     other rather than a different kind of thing. -->
			<span
				class="leading-[inherit] {done.has(li) ? 'text-neutral-600 line-through' : ''}"
				style="overflow-wrap:anywhere;word-break:break-word"
			>
				<ColorizedText text={line} />
			</span>
		</div>
	{/each}
</div>
