<script lang="ts">
	/**
	 * The progress bar for uploads in flight, pinned under the tab bar.
	 *
	 * It lives in the shell rather than on the capture screen because a big
	 * clip takes minutes and the natural thing to do while waiting is go and
	 * read the log. When this was on the capture page it vanished on
	 * navigation, and an upload you cannot see is indistinguishable from an
	 * upload that died.
	 *
	 * Deliberately thin and quiet: it is reassurance, not a task manager.
	 */
	import { uploads } from './uploads.svelte';

	const pct = $derived(Math.round(uploads.progress * 100));
	const label = $derived(
		uploads.count === 1 ? 'uploading' : `uploading ${uploads.count} files`
	);
</script>

{#if uploads.count > 0}
	<div class="sticky top-0 z-50 bg-[#14100c]">
		<div class="flex items-center gap-2 px-6 py-1 text-[10px] tracking-wide text-stone-500">
			<span>{label} · {pct}%</span>
			<span class="h-px flex-1 bg-stone-800">
				<span
					class="block h-full bg-amber-400 transition-all duration-300"
					style="width:{pct}%"
				></span>
			</span>
		</div>
	</div>
{/if}
