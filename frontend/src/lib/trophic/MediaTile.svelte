<script lang="ts">
	/**
	 * One photograph or clip, as a square in a grid.
	 *
	 * A tile is never the media itself — it is the display copy, `object-cover`
	 * into a square, and tapping it is what opens the real thing. That is the
	 * whole reason the grid can be dense: nothing here decodes a 2 GB clip, and
	 * a video tile is a poster image rather than a `<video>` element, so a day
	 * with thirty clips costs thirty JPEGs instead of thirty media pipelines.
	 *
	 * The `.view.jpg` → original fallback is the rule from `EntryMedia`: the
	 * display copy may not exist yet (video has none until a poster is
	 * captured) and may never exist (an image Pillow could not read). A video
	 * with no poster gets the black plate and the play badge, which is honest —
	 * there is nothing to show until it is opened.
	 */
	import { mediaUrl, mediaViewUrl } from './api';
	import { isVideo } from './media';

	let { ref, onopen }: { ref: string; onopen?: () => void } = $props();

	const video = $derived(isVideo(ref));

	let broken = $state(false);

	function onViewMissing(event: Event) {
		const el = event.currentTarget as HTMLImageElement;
		// One step down, then give up: the original of a video is not an image,
		// so retrying it forever would only flash a broken icon.
		if (el.src.endsWith('.view.jpg') && !video) {
			el.src = mediaUrl(ref);
		} else {
			broken = true;
		}
	}
</script>

<button
	type="button"
	class="group lift lift-sm relative aspect-square w-full overflow-hidden rounded-[10px] bg-neutral-300 shadow-sm"
	onclick={() => onopen?.()}
	aria-label={video ? 'play clip' : 'open photo'}
>
	{#if !broken}
		<img
			src={mediaViewUrl(ref)}
			alt=""
			loading="lazy"
			decoding="async"
			onerror={onViewMissing}
			class="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
		/>
	{/if}
	{#if video}
		<!-- A white chip rather than a dark scrim. On the paper ground the badge
		     has to read against a bright poster, and dimming half the frame to
		     make room for one glyph is a heavier price than it is worth. -->
		<span
			class="pointer-events-none absolute bottom-1.5 left-1.5 rounded-[5px] bg-white/[0.88] px-[5px] py-[2px] font-mono text-[9px] text-neutral-800"
		>
			▶
		</span>
	{/if}
</button>
