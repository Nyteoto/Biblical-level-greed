<script lang="ts">
	/**
	 * What an entry's attachments look like in the log.
	 *
	 * The whole media player is a `<video>` element. Nothing custom is needed
	 * for instant start or scrubbing: the backend serves media through
	 * Starlette's `FileResponse`, which answers `Range` with a 206, so the
	 * browser fetches the byte window it needs and no more. A clip starts
	 * playing without downloading, and the scrub bar works, for free.
	 *
	 * Three details that are not decoration:
	 *
	 *   - `playsinline`, or iOS hijacks the whole screen the moment you press
	 *     play, which is wrong for something being read alongside its line.
	 *   - `preload="metadata"`, so a day with thirty clips fetches thirty
	 *     headers rather than thirty videos.
	 *   - the poster and the image both point at the *display copy* and fall
	 *     back to the original on error. Video has no copy until a poster is
	 *     captured, and an image whose format Pillow could not read has none
	 *     at all — in both cases the original is still right.
	 */
	import { mediaUrl, mediaViewUrl } from './api';

	let { refs }: { refs: string[] } = $props();

	const VIDEO = /\.(mp4|mov|m4v|webm)$/i;

	function onViewMissing(event: Event, ref: string) {
		const el = event.currentTarget as HTMLImageElement;
		if (el.src.endsWith('.view.jpg')) el.src = mediaUrl(ref);
	}
</script>

{#if refs.length > 0}
	<div class="mt-1.5 flex flex-wrap gap-2">
		{#each refs as ref (ref)}
			{#if VIDEO.test(ref)}
				<!-- svelte-ignore a11y_media_has_caption -->
				<video
					src={mediaUrl(ref)}
					poster={mediaViewUrl(ref)}
					controls
					playsinline
					preload="metadata"
					class="max-h-64 max-w-full rounded border border-stone-800 bg-black"
				></video>
			{:else}
				<a href={mediaUrl(ref)} target="_blank" rel="noreferrer">
					<img
						src={mediaViewUrl(ref)}
						alt=""
						loading="lazy"
						onerror={(e) => onViewMissing(e, ref)}
						class="max-h-64 max-w-full rounded border border-stone-800 object-cover"
					/>
				</a>
			{/if}
		{/each}
	</div>
{/if}
