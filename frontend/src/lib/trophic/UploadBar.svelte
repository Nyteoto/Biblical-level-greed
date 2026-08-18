<script lang="ts">
	/**
	 * The progress of uploads in flight, as a pill in the bottom corner.
	 *
	 * It lives in the shell rather than on the capture screen because a big clip
	 * takes minutes and the natural thing to do while waiting is go and read the
	 * log. When this was on the capture page it vanished on navigation, and an
	 * upload you cannot see is indistinguishable from an upload that died.
	 *
	 * **It does not take part in layout.** It used to be a `sticky` strip across
	 * the top of the shell, which meant every upload shoved the whole app down by
	 * its height and let it back up on finishing — a page that jumps twice for
	 * something you are not even looking at. `fixed` costs the layout nothing,
	 * and the corner is where a thing you want to be able to ignore belongs.
	 *
	 * Under the glass on purpose: no `z-index` high enough to clear the scanlines,
	 * because this is part of the picture and not something laid over it.
	 *
	 * Deliberately small and quiet: it is reassurance, not a task manager.
	 */
	import { uploads } from './uploads.svelte';

	const pct = $derived(Math.round(uploads.progress * 100));
	const label = $derived(
		uploads.count === 1 ? 'uploading' : `uploading ${uploads.count} files`
	);
</script>

{#if uploads.count > 0}
	<!-- Bottom left, clear of the syntax keys and the capture line, which live
	     centre and right. The safe-area inset keeps it off the home indicator. -->
	<div
		class="upload-pill fixed bottom-0 left-0 z-40 m-4 flex w-[186px] flex-col gap-[7px] rounded-[12px] bg-surface px-3.5 py-2.5 shadow-md"
		style="animation:landing-fade-in 0.2s ease-out"
	>
		<div class="flex items-baseline gap-2 text-[11px] text-neutral-700 tabular-nums">
			<span class="min-w-0 flex-1 truncate">{label}</span>
			<span>{pct}%</span>
		</div>
		<span class="block h-[3px] overflow-hidden rounded-full bg-neutral-300">
			<span
				class="block h-full rounded-full transition-all duration-300"
				style="width:{pct}%;background:var(--gradient-accent)"
			></span>
		</span>
	</div>
{/if}

<style>
	.upload-pill {
		margin-bottom: calc(1rem + env(safe-area-inset-bottom));
		margin-left: calc(1rem + env(safe-area-inset-left));
	}
</style>
