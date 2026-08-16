<script lang="ts">
	/**
	 * Three plates at the head of an album card: the newest thing made in it,
	 * large, and the two before it beside.
	 *
	 * A project is recognised by the last thing you made in it, not by its
	 * name — which is why the lead plate is the newest and spans both rows
	 * rather than being a neat 2×2 of arbitrary shots.
	 *
	 * An album with no media at all gets the tinted fills and nothing else,
	 * deliberately: a text-only project should look like one on the shelf
	 * rather than borrow a photograph from somewhere to fill the space.
	 */
	import { mediaUrl, mediaViewUrl } from './api';

	let {
		refs,
		/** One plate filling whatever box it is given, for the one-row strips on
		 *  the shelf. The three-plate grid has its own fixed 44px rows and
		 *  cannot be scaled into a 72×54 slot without being cropped. */
		single = false
	}: { refs: string[]; single?: boolean } = $props();

	function onViewMissing(event: Event, ref: string) {
		const el = event.currentTarget as HTMLImageElement;
		// The display copy may not exist — video has none until a poster is
		// captured. One step down to the original, then give up.
		if (el.src.endsWith('.view.jpg')) el.src = mediaUrl(ref);
		else el.style.visibility = 'hidden';
	}
</script>

{#if single}
	<div class="h-full w-full overflow-hidden rounded-[10px] bg-neutral-300" aria-hidden="true">
		{#if refs[0]}
			<img
				src={mediaViewUrl(refs[0])}
				alt=""
				loading="lazy"
				decoding="async"
				onerror={(e) => onViewMissing(e, refs[0])}
				class="h-full w-full object-cover"
			/>
		{/if}
	</div>
{:else}
<div
	class="grid gap-[5px]"
	style="grid-template-columns:1.5fr 1fr;grid-template-rows:44px 44px"
	aria-hidden="true"
>
	{#each [0, 1, 2] as slot (slot)}
		{@const ref = refs[slot]}
		<div
			class="overflow-hidden rounded-[10px] bg-neutral-300 {slot === 0 ? 'row-span-2' : ''}"
		>
			{#if ref}
				<img
					src={mediaViewUrl(ref)}
					alt=""
					loading="lazy"
					decoding="async"
					onerror={(e) => onViewMissing(e, ref)}
					class="h-full w-full object-cover"
				/>
			{/if}
		</div>
	{/each}
</div>
{/if}
