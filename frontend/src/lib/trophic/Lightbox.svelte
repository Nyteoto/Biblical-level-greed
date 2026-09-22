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
	 * are painted the way they are.
	 *
	 * Video here *is* a `<video>` element with controls, unlike the tile: one
	 * at a time, opened deliberately, is exactly the case the Range-serving
	 * backend is good at.
	 *
	 * Getting out
	 * -----------
	 * Three things here are about leaving, because being unable to leave a
	 * full-screen viewer is the worst failure it has:
	 *
	 *   - **The dark is the exit.** Everywhere the photograph is not — above it,
	 *     below it, either side — dismisses. Only the picture itself, the caption
	 *     and the controls swallow the click. It used to be that the centring
	 *     container swallowed it too, which is most of the dark on a portrait
	 *     photo, so the backdrop only worked in the thin strips the container did
	 *     not cover.
	 *   - **The close button claims the status bar's inset**, via `.lightbox-top`.
	 *     This component portals onto `body` to stay out of the CRT filter, which
	 *     also takes it out of reach of every safe-area rule in `app.css` — so on
	 *     an installed phone the ✕ sat under the iOS clock and could not be hit.
	 *   - **A swipe is not a tap.** The gesture and the dismiss share a surface,
	 *     and a horizontal swipe on the backdrop would otherwise be followed by
	 *     the click that closes the viewer you were paging through.
	 */
	import { portal } from './portal';
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
	const atStart = $derived(index === 0);
	const atEnd = $derived(index === shots.length - 1);

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

	/** How far a thumb has to travel before it means "next". A thumb resting on
	 *  a photograph drifts, and a wobble must not page the gallery. */
	const SWIPE_MIN = 48;

	let touchX = 0;
	let touchY = 0;
	/** Set by a swipe, read and cleared by the click that follows it. Some
	 *  engines synthesise a click after a drag and some do not, so this is
	 *  cleared on the next `touchstart` rather than trusted to be consumed. */
	let swiped = false;
	/** A gesture that began on the video's own controls belongs to the video.
	 *  Dragging a scrubber must not also page to the next shot. */
	let ignoring = false;

	function onTouchStart(event: TouchEvent) {
		touchX = event.touches[0].clientX;
		touchY = event.touches[0].clientY;
		swiped = false;
		ignoring = !!(event.target as Element | null)?.closest?.('video');
	}

	function onTouchEnd(event: TouchEvent) {
		if (ignoring) return;
		const dx = event.changedTouches[0].clientX - touchX;
		const dy = event.changedTouches[0].clientY - touchY;
		// Horizontal only, and clearly more horizontal than vertical.
		if (Math.abs(dx) < SWIPE_MIN || Math.abs(dx) < Math.abs(dy)) return;
		swiped = true;
		step(dx < 0 ? 1 : -1);
	}

	function onBackdrop() {
		if (swiped) {
			swiped = false;
			return;
		}
		onclose();
	}

	/** Anything that is not the dark. */
	const keep = (event: MouseEvent) => event.stopPropagation();
</script>

<svelte:window {onkeydown} />

{#if shot}
	<!-- Not a `<dialog>`: it would need the whole focus-trap dance for a viewer
	     with three controls, and escape already works. -->
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		use:portal
		class="crt-exempt fixed inset-0 z-[9500] flex flex-col bg-black/95 backdrop-blur-sm"
		onclick={onBackdrop}
		ontouchstart={onTouchStart}
		ontouchend={onTouchEnd}
	>
		<div class="lightbox-top flex shrink-0 items-center justify-between pb-2 text-[12px]">
			<span class="px-2 tabular-nums text-white/55">{index + 1} / {shots.length}</span>
			<!-- 44px square, which is the smallest thing a thumb hits reliably.
			     It was a bare glyph with 8px of padding — a mouse target on a
			     screen that is mostly used with a hand. -->
			<button
				type="button"
				class="flex h-11 w-11 items-center justify-center text-[18px] text-white/70 transition-colors hover:bg-white/10 hover:text-white"
				onclick={(e) => {
					keep(e);
					onclose();
				}}
				aria-label="close"
			>
				✕
			</button>
		</div>

		<!-- The centring box does *not* stop the click: the dark either side of a
		     portrait photograph is the biggest, most obvious place to tap to get
		     out, and it lives here. Only the picture itself does. -->
		<div class="flex min-h-0 flex-1 items-center justify-center px-3">
			{#if video}
				<!-- svelte-ignore a11y_media_has_caption -->
				<!-- svelte-ignore a11y_click_events_have_key_events -->
				<!-- svelte-ignore a11y_no_static_element_interactions -->
				<video
					src={mediaUrl(shot.ref)}
					poster={mediaViewUrl(shot.ref)}
					controls
					autoplay
					playsinline
					preload="metadata"
					class="max-h-full max-w-full bg-black"
					onclick={keep}
				></video>
			{:else}
				<!-- svelte-ignore a11y_click_events_have_key_events -->
				<!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
				<img
					src={mediaViewUrl(shot.ref)}
					alt=""
					onerror={(e) => plateFallback(e, shot.ref)}
					class="max-h-full max-w-full object-contain"
					onclick={keep}
				/>
			{/if}
		</div>

		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="lightbox-bottom shrink-0 pt-4" onclick={keep}>
			{#if shot.entry.clean_text.trim()}
				<p
					class="mx-auto max-w-xl text-center text-[15px] leading-relaxed whitespace-pre-wrap text-white/85"
				>
					{shot.entry.clean_text}
				</p>
			{/if}

			<!-- Paging is a swipe first; these are what a mouse and a keyboardless
			     desktop have instead, so they are sized to be hit rather than to be
			     unobtrusive. Disabled at the ends rather than hidden: a control that
			     disappears at the edge of a set moves the other one under your
			     thumb. -->
			<div class="mt-4 flex items-center justify-center gap-3">
				<button
					type="button"
					class="flex h-11 w-11 items-center justify-center text-[20px] text-white/70 transition-colors hover:bg-white/10 hover:text-white disabled:opacity-20 disabled:hover:bg-transparent"
					disabled={atStart}
					aria-label="previous"
					onclick={() => step(-1)}
				>
					‹
				</button>
				<a
					href="/media/{shot.ref}"
					target="_blank"
					rel="noreferrer"
					class=" px-4 py-3 text-[12px] text-white/55 transition-colors hover:bg-white/10 hover:text-white"
				>
					original
				</a>
				<button
					type="button"
					class="flex h-11 w-11 items-center justify-center text-[20px] text-white/70 transition-colors hover:bg-white/10 hover:text-white disabled:opacity-20 disabled:hover:bg-transparent"
					disabled={atEnd}
					aria-label="next"
					onclick={() => step(1)}
				>
					›
				</button>
			</div>
		</div>
	</div>
{/if}
