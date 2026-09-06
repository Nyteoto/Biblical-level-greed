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
	import { clockFace, duration, timer } from './timer.svelte';
	import Glyph from './Glyph.svelte';

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
	const pom = $derived(clock.pomodoro);

	/**
	 * The big digits.
	 *
	 * A stopwatch counts up and shows the clock. A pomodoro shows **what is
	 * left of the stretch you are in**, counting down, because that is the
	 * question it exists to answer — a pomodoro that displayed total elapsed
	 * time would be a stopwatch wearing a phase label. The total is still on
	 * screen, small, under the controls.
	 */
	const face = $derived(
		pom ? clockFace(Math.ceil(pom.remainingMs / 1000)) : clockFace(clock.elapsedSeconds)
	);

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
			<span
				class="text-[10px] font-bold tracking-[0.22em] uppercase
				       {pom?.phase === 'rest' ? 'text-neutral-600' : 'text-ink'}"
			>
				<!-- The kicker carries the phase, because in a pomodoro it is the
				     one word that changes what the big number means. `resting` is
				     dimmed and `working` is lit: the screen should be readable
				     from across the room as one of two states without reading
				     anything at all. -->
				{pom ? (pom.phase === 'work' ? 'working' : 'resting') : 'clocking'}
			</span>
			<span class="text-[17px] font-semibold text-neutral-800">{session.folderName}</span>

			<!-- Completed cycles, as marks. A count would be a number next to
			     two other numbers; the marks say "four of these have happened"
			     without joining the arithmetic on the rest of the screen. Capped
			     so a long afternoon does not draw a hundred of them. -->
			{#if pom && pom.cycles > 0}
				<div class="flex items-center gap-1.5" title="{pom.cycles} completed">
					{#each Array(Math.min(pom.cycles, 8)) as _, i (i)}
						<span class="h-[5px] w-[5px] rounded-full bg-neutral-600"></span>
					{/each}
					{#if pom.cycles > 8}
						<span class="text-[11px] text-neutral-600 tabular-nums">+{pom.cycles - 8}</span>
					{/if}
				</div>
			{/if}
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

		<!-- ── What this timer is ──────────────────────────────────────────
		     Under the primary controls, not above them: the mode is a thing you
		     set once and then forget, while start and stop are the reason the
		     screen exists. The lengths only appear in pomodoro mode, because a
		     stopwatch has nothing to be told. -->
		<div class="flex flex-col items-center gap-3 text-[12px] text-neutral-600">
			<div class="flex items-center gap-1 rounded-[10px] bg-neutral-200 p-1">
				{#each [['stopwatch', 'stopwatch'], ['pomodoro', 'pomodoro']] as const as [value, label] (value)}
					<button
						type="button"
						aria-pressed={clock.mode === value}
						class="rounded-lg px-3 py-1 transition-colors {clock.mode === value
							? 'bg-surface font-semibold text-ink shadow-sm'
							: 'hover:text-ink'}"
						onclick={() => clock.setMode(value)}
					>
						{label}
					</button>
				{/each}
			</div>

			{#if pom}
				<div class="flex items-center gap-4">
					<label class="flex items-center gap-2">
						<span>work</span>
						<input
							type="number"
							min="1"
							max="240"
							class="w-[52px] rounded-lg bg-surface px-2 py-1 text-center tabular-nums
							       text-neutral-800 shadow-sm outline-none focus:text-ink"
							value={clock.workMin}
							onchange={(e) => {
								clock.setLengths(e.currentTarget.valueAsNumber, clock.restMin);
								// The running session keeps the lengths it started
								// with; re-selecting the mode is what adopts the new
								// ones, and doing it here is what makes the input
								// look like it did something.
								clock.setMode('pomodoro');
							}}
						/>
						<span>min</span>
					</label>
					<label class="flex items-center gap-2">
						<span>rest</span>
						<input
							type="number"
							min="1"
							max="240"
							class="w-[52px] rounded-lg bg-surface px-2 py-1 text-center tabular-nums
							       text-neutral-800 shadow-sm outline-none focus:text-ink"
							value={clock.restMin}
							onchange={(e) => {
								clock.setLengths(clock.workMin, e.currentTarget.valueAsNumber);
								clock.setMode('pomodoro');
							}}
						/>
						<span>min</span>
					</label>
					<button
						type="button"
						aria-pressed={clock.muted}
						class="rounded-lg px-2 py-1 {clock.muted ? 'text-neutral-600' : 'text-ink'}"
						title={clock.muted ? 'chime off' : 'chime on'}
						onclick={() => clock.setMuted(!clock.muted)}
					>
						{clock.muted ? 'chime off' : 'chime on'}
					</button>
				</div>
			{/if}

			<!-- What will actually be written when you stop. In a stopwatch this
			     is the clock above, so it is not repeated; in a pomodoro the
			     clock above is a countdown and the banked work is the number
			     that matters, so it is said once, here, and nowhere else. -->
			{#if pom}
				<div class="flex items-center gap-1.5">
					<Glyph kind="time" size={12} align="center" />
					<span class="tabular-nums">{duration(clock.workedSeconds)} worked</span>
					<span class="text-neutral-500">·</span>
					<span class="tabular-nums">{clockFace(clock.elapsedSeconds)} on the clock</span>
				</div>
			{/if}
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
