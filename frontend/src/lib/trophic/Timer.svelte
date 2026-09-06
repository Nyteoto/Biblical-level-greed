<script lang="ts">
	/**
	 * The running timer, taking the whole screen.
	 *
	 * It takes the screen rather than sitting in a corner because that is the
	 * honest shape of the thing: a timer you can see past is a timer you forget
	 * is running, and a forgotten timer is the only way this feature produces a
	 * wrong number. A screen with one clock on it and two controls cannot be
	 * left running by accident.
	 *
	 * **It is deliberately not `crt-exempt`.** The lightbox opts out of the
	 * monitor layers because a full-size photograph must never be scanlined;
	 * this is the opposite kind of thing — it is the app talking, and the
	 * scanlines, the glow and the vignette are what make it read as this app
	 * rather than as a web page that opened on top of it. So it sits below
	 * z-9000, where the glass covers it.
	 *
	 * The digits are the only large thing here, and they do not animate. A
	 * pulsing or sweeping clock is read as a progress bar — as though the app
	 * were counting towards something — and this counts away from a start with
	 * no target at all. The one moving thing is the seconds place.
	 */
	import { clockFace, timer } from './timer.svelte';

	let {
		onstop,
		ondiscard,
		onclose
	}: {
		/** Stop and log. The parent owns the send, because the parent is what
		 *  has to put the number back on the screen behind this one. */
		onstop: () => void;
		/** Throw the session away. Confirmed here first. */
		ondiscard: () => void;
		/** Leave the screen with the timer untouched and still running. */
		onclose: () => void;
	} = $props();

	const clock = timer();

	const session = $derived(clock.session);
	const face = $derived(clockFace(clock.elapsedSeconds));

	/** Confirm a discard, because it is the one control here that destroys a
	 *  measurement — and unlike everything else in this app, an unlogged
	 *  session has never been written anywhere and cannot be recovered by
	 *  appending anything. */
	let confirming = $state(false);

	function onkeydown(event: KeyboardEvent) {
		// Space is the timer's own key: it is what a stopwatch answers to, and
		// there is no text on this screen for it to belong to instead.
		if (event.key === ' ' || event.code === 'Space') {
			event.preventDefault();
			if (clock.running) clock.pause();
			else if (session) clock.start(session.folderId, session.folderName);
			return;
		}
		// Escape leaves the timer *running* and goes back. It is a way out of
		// the screen, not a way out of the session — losing time to a reflex
		// press of Escape is exactly the mistake this must not make. It backs
		// out of the discard prompt first, for the same reason.
		if (event.key === 'Escape') {
			event.preventDefault();
			if (confirming) confirming = false;
			else onclose();
		}
	}

</script>

<svelte:window on:keydown={onkeydown} />

{#if session}
	<div
		class="fixed inset-0 z-[8000] flex flex-col items-center justify-center gap-10 bg-ground"
		role="dialog"
		aria-modal="true"
		aria-label="Timer for {session.folderName}"
	>
		<!-- Which folder this is time *for*. Small, above the clock: you opened
		     this from that folder's page and already know, so it is a
		     confirmation rather than a heading. -->
		<div class="flex flex-col items-center gap-2">
			<span class="text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">
				clocking
			</span>
			<span class="text-[17px] font-semibold text-neutral-800">{session.folderName}</span>
		</div>

		<!-- `tabular-nums` so the digits do not shuffle sideways once a second,
		     which is the single most distracting thing a clock can do. -->
		<div
			class="text-[19vw] leading-none font-extrabold tracking-[-0.04em] tabular-nums text-ink
			       sm:text-[15vw] md:text-[160px]"
			aria-live="off"
		>
			{face}
		</div>

		<div class="flex items-center gap-3">
			{#if clock.running}
				<button
					type="button"
					class="lift lift-sm rounded-lg bg-surface px-5 py-2.5 text-[13px] font-semibold
					       text-neutral-800 shadow-sm"
					onclick={() => clock.pause()}
				>
					pause
				</button>
			{:else}
				<button
					type="button"
					class="lift lift-sm rounded-lg bg-surface px-5 py-2.5 text-[13px] font-semibold
					       text-ink shadow-sm"
					onclick={() => clock.start(session.folderId, session.folderName)}
				>
					resume
				</button>
			{/if}

			<button
				type="button"
				class="rounded-lg bg-ink px-5 py-2.5 text-[13px] font-bold text-ground"
				onclick={onstop}
			>
				stop &amp; log
			</button>
		</div>

		<!-- The two ways out that are not "log it", kept small and far from the
		     primary. `back` is the ordinary one — the timer goes on running and
		     the app is usable, which is the point of it being a timer rather
		     than a modal you are trapped in. -->
		<div class="flex items-center gap-5 text-[12px] text-neutral-600">
			<button type="button" class="hover:text-ink" onclick={onclose}>
				back — keep running
			</button>
			{#if confirming}
				<span class="text-error">
					discard {clockFace(clock.elapsedSeconds)}?
					<button
						type="button"
						class="ml-1 font-bold underline"
						onclick={() => {
							confirming = false;
							ondiscard();
						}}
					>
						yes
					</button>
					<button type="button" class="ml-2 underline" onclick={() => (confirming = false)}>
						no
					</button>
				</span>
			{:else}
				<button type="button" class="hover:text-error" onclick={() => (confirming = true)}>
					discard
				</button>
			{/if}
		</div>
	</div>
{/if}
