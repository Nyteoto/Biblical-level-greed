<script lang="ts">
	/**
	 * What you can do to a chapter, opened where you held it.
	 *
	 * Two things: what it is called, and whether the cut stands at all.
	 *
	 * This panel used to offer one, and the difference is the whole of step 4.
	 * A chapter was a run of consecutive months the app found and named from the
	 * commonest word inside it, so the only thing you could do was overrule the
	 * name — there was no cut to take back, because you had not made one. Now
	 * the cut is the chapter: removing it does not delete anything written, it
	 * joins these entries to the chapter before them.
	 *
	 * The months are printed under the name because the chapter is a *stretch
	 * of time*, and it is the only thing a name can hide. `Feb–May` says what
	 * you are about to rename or un-cut. A chapter with no name yet is drawn as
	 * its range instead, in the neutral grey — the panel never invents a word
	 * for it, and neither does anything else.
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
		armed = false,
		onrename,
		onremove,
		onclose
	}: {
		x: number;
		y: number;
		chapter: Chapter;
		/** Passed straight through: a click opened this, not a hold, so there
		 *  is no release for the shell to absorb. See `HoldMenu`. */
		armed?: boolean;
		/** The cut comes back with the name, because the cut is what a rename
		 *  is addressed to and *this* is the component that still has it.
		 *  Asking the caller to read it off its own `{@const}` after the panel
		 *  closes is asking it to read a scope that is being torn down — see
		 *  the note beside the media panels on the reading lens, and the three
		 *  handlers that had that bug. */
		onrename: (to: string, at: string) => void;
		/** Take the cut back. Same argument for carrying the month. */
		onremove: (at: string) => void;
		onclose: () => void;
	} = $props();

	let renaming = $state(false);
	let value = $state('');

	function submit() {
		const next = value.trim();
		renaming = false;
		if (!next || next === chapter.name) return;
		onrename(next, chapter.month);
	}
</script>

<HoldMenu {x} {y} {armed} {onclose}>
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
				class="w-full bg-neutral-200 px-2.5 py-1.5 text-[13px]"
				onkeydown={(e) => {
					if (e.key === 'Escape') renaming = false;
				}}
				onblur={submit}
			/>
		</form>
	{:else}
		<div class="px-3.5 pt-2.5 pb-2">
			<div class="truncate text-[14px] font-bold {chapter.name ? '' : 'text-neutral-700'}">
				{chapter.name || chapter.range}
			</div>
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
			{chapter.name ? 'Rename chapter' : 'Name it'}
		</button>

		<!-- Said as what happens rather than as "delete": nothing written is
		     touched, and the entries have somewhere to go. That sentence is the
		     thing you want to know before pressing it, so it is on the panel and
		     not behind a confirm. -->
		<button
			type="button"
			class="px-3.5 pt-2 pb-2.5 text-left transition-colors hover:bg-neutral-200"
			onclick={() => onremove(chapter.month)}
		>
			<span class="text-[13px] text-accent-700">Take the cut back</span>
			<span class="mt-0.5 block text-[11px] leading-[1.4] text-neutral-700">
				these entries join the chapter before them
			</span>
		</button>
	{/if}
</HoldMenu>
