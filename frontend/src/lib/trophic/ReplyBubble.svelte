<script lang="ts">
	/**
	 * A reply, with whatever came attached to it.
	 *
	 * One component because a reply has to look the same on both day shapes, and
	 * because the thing that went wrong before was exactly this being decided in
	 * two places: the bubble lived in `LeadDay` and `LightDay`, the *media* lived
	 * in the day's own ribbon, and a reply that carried a photograph quietly
	 * stopped being drawn as a reply at all. On the lead day it was worse than
	 * that — the photograph was promoted to the day's hero and the reply became
	 * its caption, left-aligned and unlinked, which is the one shape that says
	 * "this is not part of a conversation".
	 *
	 * **The picture goes inside the bubble.** That is what makes it read as a
	 * message rather than as a photograph that happens to share a day with one,
	 * and it is the whole reason to have a bubble in the first place. The
	 * consequence for both day shapes is that a reply's attachments come *out*
	 * of the day's contact strip — they are spoken for, and showing them twice
	 * would be the app saying the same thing in two places.
	 *
	 * Two click targets, because there are two different things to want:
	 * the picture opens, the words follow the thread back. When there are no
	 * words there is a line saying so, which is also the way back — a reply that
	 * is only a photograph still has somewhere to point.
	 */
	import ColorizedText from './ColorizedText.svelte';
	import { mediaViewUrl } from './api';
	import { isVideo, plateFallback, type Shot } from './media';
	import type { Entry } from './api';

	let {
		entry,
		onjump,
		onopen
	}: {
		entry: Entry;
		onjump?: (entryId: string) => void;
		/** The reply's *own* attachments, and which was clicked. Its own list
		 *  rather than the day's: these are this message's, and paging sideways
		 *  out of them into the rest of the day would be a different gesture. */
		onopen?: (shots: Shot[], index: number) => void;
	} = $props();

	const shots = $derived((entry.media ?? []).map((ref) => ({ ref, entry })));
	const said = $derived(entry.clean_text.trim().length > 0);
</script>

<div class="reply-bubble flex min-w-0 flex-col gap-2">
	{#if shots.length}
		<!-- Two up at most: a bubble is a message, and a message with a contact
		     sheet in it is an album. The rest stay in the day's strip. -->
		<div class="grid gap-[5px] {shots.length > 1 ? 'grid-cols-2' : 'grid-cols-1'}">
			{#each shots.slice(0, 4) as shot, i (shot.ref)}
				<button
					type="button"
					class="lift lift-sm relative overflow-hidden rounded-[9px] bg-neutral-300"
					style="max-width:260px"
					onclick={() => onopen?.(shots, i)}
					aria-label={isVideo(shot.ref) ? 'play clip' : 'open photo'}
				>
					<img
						src={mediaViewUrl(shot.ref)}
						alt=""
						loading="lazy"
						decoding="async"
						class="block h-full max-h-[190px] w-full object-cover"
						onerror={(e) => plateFallback(e, shot.ref)}
					/>
				</button>
			{/each}
		</div>
	{/if}

	{#if said}
		<button
			type="button"
			class="min-w-0 text-left leading-[inherit]"
			style="overflow-wrap:anywhere"
			title="jump to the thought this answers"
			onclick={() => onjump?.(entry.reply_to)}
		>
			<ColorizedText text={entry.clean_text} />
		</button>
	{:else}
		<!-- Only a photograph. It is still an answer to something, so it still
		     has a way back. -->
		<button
			type="button"
			class="self-end text-[11px] text-neutral-600 transition-colors hover:text-neutral-800"
			title="jump to the thought this answers"
			onclick={() => onjump?.(entry.reply_to)}
		>
			in reply ↩
		</button>
	{/if}
</div>
