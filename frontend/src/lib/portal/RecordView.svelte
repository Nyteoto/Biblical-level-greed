<script lang="ts">
	/**
	 * A sealed Record, as the next Instance reads it. Nothing here is editable
	 * and nothing offers to be: the page draws what was committed, in the order
	 * the template asked for it, and the print (`pdf.py`) keeps the same order
	 * so the screen and the paper are the same document.
	 *
	 * Video plays here, which is the one thing the print cannot do — on paper a
	 * clip is its poster frame and its filename.
	 */
	import { mediaUrl, pdfUrl, viewUrl, type SealedRecord } from '$lib/api';
	import MoodScale from './MoodScale.svelte';
	import { longDay } from './rules';

	let { record }: { record: SealedRecord } = $props();

	/** An undecodable image has no display copy; show the original instead. */
	function fallback(event: Event, ref: string) {
		const img = event.currentTarget as HTMLImageElement;
		if (!img.src.endsWith(mediaUrl(ref))) img.src = mediaUrl(ref);
	}
</script>

<article class="flex flex-col gap-10">
	<header class="flex flex-wrap items-start justify-between gap-6">
		<div class="flex flex-col gap-3">
			<span class="p-label">{longDay(record.day)}</span>
			<h1 class="p-title">Instance {record.instance}</h1>
		</div>
		<img
			src={viewUrl(record.selfie)}
			alt="Instance {record.instance}"
			class="h-[168px] w-[126px] object-cover"
			onerror={(e) => fallback(e, record.selfie)}
		/>
	</header>

	{#if record.media.length}
		<section class="flex flex-col gap-3">
			<h2 class="p-label">Media</h2>
			<div class="grid grid-cols-1 gap-6 sm:grid-cols-2">
				{#each record.media as item (item.ref)}
					<figure class="flex flex-col gap-2">
						{#if item.kind === 'video'}
							<!-- svelte-ignore a11y_media_has_caption -->
							<video
								src={mediaUrl(item.ref)}
								poster={viewUrl(item.ref)}
								controls
								playsinline
								preload="metadata"
								class="aspect-video w-full bg-neutral-200 object-contain"
							></video>
						{:else}
							<a href={mediaUrl(item.ref)} target="_blank" rel="noopener">
								<img
									src={viewUrl(item.ref)}
									alt={item.caption}
									class="max-h-[420px] w-full bg-neutral-200 object-contain"
									onerror={(e) => fallback(e, item.ref)}
								/>
							</a>
						{/if}
						{#if item.caption}
							<figcaption class="text-[12px] leading-[1.6] text-neutral-600">
								{item.caption}
							</figcaption>
						{/if}
					</figure>
				{/each}
			</div>
		</section>
	{/if}

	<section class="flex max-w-[68ch] flex-col gap-3">
		<h2 class="p-label">Record</h2>
		<p class="text-[14px] leading-[1.75] whitespace-pre-wrap text-neutral-800">{record.body}</p>
	</section>

	<section class="flex max-w-[68ch] flex-col gap-3">
		<h2 class="p-label">What do you want {record.instance + 1} to do?</h2>
		<p class="text-[14px] leading-[1.75] whitespace-pre-wrap text-neutral-800">{record.wish}</p>
	</section>

	<section class="flex flex-col gap-3">
		<h2 class="p-label">On a scale of 1 to 10, how do you feel?</h2>
		<MoodScale value={record.mood} />
	</section>

	<section class="flex flex-col gap-2">
		<h2 class="p-label">Signed</h2>
		<p class="text-[22px] font-extrabold tracking-[-0.02em] text-ink">{record.signature}</p>
	</section>

	{#if record.pdf}
		<a
			href={pdfUrl(record.instance)}
			target="_blank"
			rel="noopener"
			class="self-start text-[12px] text-neutral-600 transition-colors hover:text-ink"
			>{record.instance}.pdf ↗</a
		>
	{/if}
</article>
