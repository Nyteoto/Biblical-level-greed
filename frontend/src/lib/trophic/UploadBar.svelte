<script lang="ts">
	/**
	 * The progress of uploads in flight, as a pill along the bottom edge.
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
	 * and the foot of the screen is where a thing you want to be able to ignore
	 * belongs.
	 *
	 * Under the glass on purpose: no `z-index` high enough to clear the scanlines,
	 * because this is part of the picture and not something laid over it.
	 *
	 * Deliberately small and quiet: it is reassurance, not a task manager.
	 *
	 * **A failure is the one thing here that asks for something.** It has to:
	 * the line it belonged to is already in the log, so a photograph that did
	 * not go up leaves an entry that is quietly missing half of what you meant
	 * by it, and nothing anywhere else in the app would ever say so. It takes
	 * the refusal colour every other refusal takes, it names a count rather
	 * than a filename because the count is the part you can act on, and it
	 * offers the two things there are to do. It does not time out — this is
	 * the one pill you have to answer.
	 */
	import { uploads, retryFailed, dismissFailed } from './uploads.svelte';

	const pct = $derived(Math.round(uploads.progress * 100));
	const label = $derived(
		uploads.count === 1 ? 'uploading' : `uploading ${uploads.count} files`
	);

	const lost = $derived(uploads.failed.length);
	const lostLabel = $derived(
		lost === 1 ? 'a file did not send' : `${lost} files did not send`
	);
</script>

{#if uploads.count > 0}
	<!-- Bottom centre. It was in the bottom-left corner, which is where the
	     capture screen's tally sticker now stands — and a progress pill laid over
	     a thing you can pick up and turn is two objects in one place. Centred, it
	     is still below everything the column holds: the syntax keys are the last
	     of that and they end well above the foot.
	     The safe-area inset keeps it off the home indicator. -->
	<div
		class="upload-pill fixed bottom-0 left-1/2 z-40 mb-4 flex w-[186px] -translate-x-1/2 flex-col gap-[7px] rounded-[12px] bg-surface px-3.5 py-2.5 shadow-md"
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

<!-- Above the progress pill when both are up: what failed outranks what is
     still going, and the two never share the same line of the screen. -->
{#if lost > 0}
	<div
		class="upload-pill fixed bottom-0 left-1/2 z-40 mb-4 flex w-[228px] -translate-x-1/2 flex-col gap-2 rounded-[12px] bg-surface px-3.5 py-2.5 shadow-md"
		class:stacked={uploads.count > 0}
		style="animation:landing-fade-in 0.2s ease-out"
		role="alert"
	>
		<div class="flex items-center gap-2">
			<!-- The thumbnails, so it is clear which pictures are being talked
			     about. Three at most: past that the count is the honest summary
			     and a row of stamps is just a row of stamps. -->
			{#each uploads.failed.slice(0, 3) as f (f.item.key)}
				{#if f.item.kind === 'image'}
					<img
						src={f.item.preview}
						alt=""
						class="h-7 w-7 shrink-0 rounded-[5px] object-cover opacity-70"
					/>
				{:else}
					<!-- A clip's preview is a video object URL and an <img> cannot
					     draw it. A stamp saying what it is beats a broken one. -->
					<span
						class="flex h-7 w-7 shrink-0 items-center justify-center rounded-[5px] bg-neutral-200 font-mono text-[8px] text-neutral-700"
					>
						clip
					</span>
				{/if}
			{/each}
			<span class="min-w-0 flex-1 truncate text-[11px] text-accent-700">{lostLabel}</span>
		</div>
		<div class="flex gap-1.5">
			<button
				type="button"
				class="lift lift-sm flex-1 rounded-lg bg-ground px-2 py-1 text-[11px] font-semibold text-ink shadow-sm"
				onclick={retryFailed}
			>
				try again
			</button>
			<button
				type="button"
				class="rounded-lg px-2 py-1 text-[11px] text-neutral-600 transition-colors hover:text-ink"
				onclick={dismissFailed}
			>
				let it go
			</button>
		</div>
	</div>
{/if}

<style>
	.upload-pill {
		margin-bottom: calc(1rem + env(safe-area-inset-bottom));
	}

	/* Clears the progress pill when both are on screen. Its height plus the
	   gap — measured, not guessed, and it only has to hold for the one pill
	   this can ever stack above. */
	.stacked {
		margin-bottom: calc(1rem + 62px + env(safe-area-inset-bottom));
	}
</style>
