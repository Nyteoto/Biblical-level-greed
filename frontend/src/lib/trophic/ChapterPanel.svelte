<script lang="ts">
	/**
	 * What you can do to a chapter, opened where you held it.
	 *
	 * There is one thing, which is what it is called — and that is the whole
	 * reason this panel exists. A chapter is the only heading in the app the app
	 * wrote itself: a run of months named from the commonest word inside it,
	 * which is right often enough to be worth doing and wrong often enough that
	 * being unable to overrule it was the irritating part.
	 *
	 * So the panel says which reading it is showing you. A chapter still wearing
	 * the word it was named from offers a rename and nothing else; one you have
	 * named offers the way back as well, spelled as what it would go back to
	 * rather than as "reset" — the point of the line is the name you would get,
	 * not the act of clearing something.
	 *
	 * The months are printed under it because the chapter is a *stretch of
	 * time*, and it is the only thing the name is attached to that a name can
	 * hide. `Feb–May` says what you are about to rename.
	 *
	 * The backdrop, the position, and the rule that a hold's own release must
	 * not dismiss what it opened all live in `HoldMenu` — the same as the group
	 * panel this is modelled on.
	 */
	import HoldMenu from './HoldMenu.svelte';
	import type { Chapter } from './api';

	let {
		x,
		y,
		chapter,
		onrename,
		onclose
	}: {
		x: number;
		y: number;
		chapter: Chapter;
		/** An empty string hands it back to the reader.
		 *
		 *  The chapter's first month comes back with it, because the month is
		 *  what the name is anchored to and *this* is the component that still
		 *  has it. Asking the caller to read it off its own `{@const}` after the
		 *  panel closes is asking it to read a scope that is being torn down —
		 *  see the note beside the media panels on the album screen, and the
		 *  three handlers that had that bug. */
		onrename: (to: string, at: number) => void;
		onclose: () => void;
	} = $props();

	let renaming = $state(false);
	let value = $state('');

	function submit() {
		const next = value.trim();
		renaming = false;
		if (!next || next === chapter.name) return;
		onrename(next, chapter.first_month);
	}
</script>

<HoldMenu {x} {y} {onclose}>
	{#if renaming}
		<form
			onsubmit={(e) => {
				e.preventDefault();
				submit();
			}}
			class="px-3 py-2"
		>
			<!-- svelte-ignore a11y_autofocus -->
			<input
				bind:value
				autofocus
				spellcheck="false"
				class="w-full rounded-lg bg-neutral-200 px-2.5 py-1.5 text-[13px]"
				onkeydown={(e) => {
					if (e.key === 'Escape') renaming = false;
				}}
				onblur={submit}
			/>
		</form>
	{:else}
		<div class="px-3.5 pt-2.5 pb-2">
			<div class="truncate text-[14px] font-bold">{chapter.name}</div>
			<div class="text-[11px] text-neutral-700">
				{chapter.range} · {chapter.entries}
				{chapter.entries === 1 ? 'entry' : 'entries'}
			</div>
		</div>

		<button
			type="button"
			class="px-3.5 py-2 text-left text-[13px] transition-colors hover:bg-neutral-200"
			onclick={() => {
				value = chapter.name;
				renaming = true;
			}}
		>
			Rename chapter
		</button>

		{#if chapter.named && chapter.derived && chapter.derived !== chapter.name}
			<!-- Named as what it goes back to, not as "reset": the name is the
			     thing you are choosing between, and the reader's one is a real
			     answer rather than an absence. -->
			<button
				type="button"
				class="px-3.5 py-2 text-left text-[13px] text-neutral-700 transition-colors hover:bg-neutral-200 hover:text-ink"
				onclick={() => onrename('', chapter.first_month)}
			>
				Call it <span class="font-semibold">{chapter.derived}</span> again
			</button>
		{/if}
	{/if}
</HoldMenu>
