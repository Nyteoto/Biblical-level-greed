<script lang="ts">
	/**
	 * Full-screen media, with the line it was written beside underneath.
	 *
	 * The tiles are a density display; this is where something is actually
	 * looked at. It takes the whole day's media as one flat list so the arrows
	 * cross entry boundaries — you scrubbed through a day, not through one
	 * capture, and stopping at the edge of an entry would be an artefact of
	 * how the words happened to be split up.
	 *
	 * The caption is the entry's clean text, uncolourised on purpose: over a
	 * photograph the syntax colours read as damage to the image. The tags are
	 * still legible in the log itself, one tap away.
	 *
	 * The backdrop stays dark, and that is the one place in this app that is not
 * on the paper ground. A photograph is looked at against black — a light
 * surround shifts how its own tones read, which is the whole reason galleries
 * are painted the way they are. The chrome around it is white rather than
 * stone so it belongs to this design.
 *
 * Video here *is* a `<video>` element with controls, unlike the tile: one
	 * at a time, opened deliberately, is exactly the case the Range-serving
	 * backend is good at.
	 */
	import { mediaUrl, mediaViewUrl } from './api';
	import { isVideo, plateFallback, type Shot } from './media';

	let {
		shots,
		index,
		onclose,
		onindex
	}: {
		shots: Shot[];
		index: number;
		onclose: () => void;
		onindex: (index: number) => void;
	} = $props();

	const shot = $derived(shots[index]);
	const video = $derived(shot ? isVideo(shot.ref) : false);

	function step(delta: number) {
		const next = index + delta;
		if (next >= 0 && next < shots.length) onindex(next);
	}

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') onclose();
		else if (event.key === 'ArrowLeft') step(-1);
		else if (event.key === 'ArrowRight') step(1);
		else return;
		event.preventDefault();
	}

	// Swipe, because this is mostly read on a tablet. Horizontal only, and only
	// past a threshold — a thumb resting on a photograph drifts, and a 12px
	// wobble must not count as "next".
	let touchX = 0;
	let touchY = 0;

	function onTouchStart(event: TouchEvent) {
		touchX = event.touches[0].clientX;
		touchY = event.touches[0].clientY;
	}

	function onTouchEnd(event: TouchEvent) {
		const dx = event.changedTouches[0].clientX - touchX;
		const dy = event.changedTouches[0].clientY - touchY;
		if (Math.abs(dx) < 48 || Math.abs(dx) < Math.abs(dy)) return;
		step(dx < 0 ? 1 : -1);
	}

</script>

<svelte:window {onkeydown} />

{#if shot}
	<!-- The backdrop closes; everything inside it stops the click. Not a
	     `<dialog>`: it would need the whole focus-trap dance for a viewer with
	     three controls, and escape already works. -->
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		class="fixed inset-0 z-[200] flex flex-col bg-black/95 backdrop-blur-sm"
		onclick={onclose}
		ontouchstart={onTouchStart}
		ontouchend={onTouchEnd}
	>
		<div class="flex items-center justify-between px-6 py-4 text-[12px] text-white/55">
			<span class="tabular-nums">{index + 1} / {shots.length}</span>
			<button
				type="button"
				class="px-2 text-white/70 transition-colors hover:text-white"
				onclick={onclose}
				aria-label="close"
			>
				✕
			</button>
		</div>

		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<div class="flex min-h-0 flex-1 items-center justify-center px-3" onclick={(e) => e.stopPropagation()}>
			{#if video}
				<!-- svelte-ignore a11y_media_has_caption -->
				<video
					src={mediaUrl(shot.ref)}
					poster={mediaViewUrl(shot.ref)}
					controls
					autoplay
					playsinline
					preload="metadata"
					class="max-h-full max-w-full rounded-[12px] bg-black"
				></video>
			{:else}
				<img
					src={mediaViewUrl(shot.ref)}
					alt=""
					onerror={(e) => plateFallback(e, shot.ref)}
					class="max-h-full max-w-full rounded-[12px] object-contain"
				/>
			{/if}
		</div>

		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<div class="shrink-0 px-6 pt-4 pb-8" onclick={(e) => e.stopPropagation()}>
			{#if shot.entry.clean_text.trim()}
				<p class="mx-auto max-w-xl text-center text-[15px] leading-relaxed whitespace-pre-wrap text-white/85">
					{shot.entry.clean_text}
				</p>
			{/if}
			<div class="mt-4 flex items-center justify-center gap-6 text-[12px] text-white/55">
				<button
					type="button"
					class="px-3 py-1 transition-colors hover:text-white disabled:opacity-25"
					disabled={index === 0}
					onclick={() => step(-1)}
				>
					← prev
				</button>
				<a href="/media/{shot.ref}" target="_blank" rel="noreferrer" class="hover:text-white">
					original
				</a>
				<button
					type="button"
					class="px-3 py-1 transition-colors hover:text-white disabled:opacity-25"
					disabled={index === shots.length - 1}
					onclick={() => step(1)}
				>
					next →
				</button>
			</div>
		</div>
	</div>
{/if}
