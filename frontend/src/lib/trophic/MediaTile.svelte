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
	 * What happens when the display copy will not load is `plateFallback` in
	 * `media.ts`, shared with the ribbon, the mosaic and the lightbox so that a
	 * missing poster looks the same wherever you meet it. A clip with none gets
	 * the tinted plate and the play badge, which is honest — there is nothing
	 * to show until it is opened.
	 */
	import { mediaViewUrl } from './api';
	import { hold } from './hold';
	import { isVideo, plateFallback } from './media';

	let {
		ref,
		onopen,
		/** Hold a tile for what can be done with the picture rather than to it —
		 *  see the album's overview. Tiles without a handler simply do not claim
		 *  the gesture, and the ring says so. */
		onhold
	}: { ref: string; onopen?: () => void; onhold?: (x: number, y: number) => void } = $props();

	const video = $derived(isVideo(ref));
</script>

<button
	type="button"
	class="group lift lift-sm relative aspect-square w-full overflow-hidden bg-neutral-300 shadow-sm"
	use:hold={(x, y) => onhold?.(x, y)}
	onclick={() => onopen?.()}
	aria-label={video ? 'play clip' : 'open photo'}
>
	<img
		src={mediaViewUrl(ref)}
		alt=""
		loading="lazy"
		decoding="async"
		onerror={(e) => plateFallback(e, ref)}
		class="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
	/>
	{#if video}
		<!-- A white chip rather than a dark scrim. On the paper ground the badge
		     has to read against a bright poster, and dimming half the frame to
		     make room for one glyph is a heavier price than it is worth. -->
		<span
			class="pointer-events-none absolute bottom-1.5 left-1.5 bg-ground/85 px-[5px] py-[2px] font-mono text-[9px] text-neutral-800"
		>
			▶
		</span>
	{/if}
</button>
