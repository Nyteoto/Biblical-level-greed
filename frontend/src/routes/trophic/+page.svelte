<script lang="ts">
	/**
	 * The capture bar. Ported from `screens/CaptureClient.tsx`, with the timings
	 * in CAPTURE-BAR.md treated as the specification they say they are.
	 *
	 * What the numbers below are doing, since none of them are defaults:
	 *   600ms  typing glow decays after the last keystroke
	 *   0.1s / 0.4s  the glow's fade in / out — fast in, slow out, never equal
	 *   220ms  the draft slides out on send, 110% so no sliver is left behind
	 *   900ms  the indicator holds green
	 *   500ms / 400ms  shake state / shake animation; the state outlives the
	 *          animation so a fast re-submit cannot restart it mid-flight
	 *   2000ms "Nope" stays up after a pasted link
	 *   4000ms of stillness before the chrome dims (and 30s to come back)
	 *   300ms  before autofocus on mount
	 *
	 * There is deliberately no feed on this screen. The capture bar is for
	 * getting a thought out of your head; reading them back is the log's job.
	 */
	import { goto } from '$app/navigation';
	import SmoothTextarea from '$lib/trophic/SmoothTextarea.svelte';
	import SyntaxBar from '$lib/trophic/SyntaxBar.svelte';
	import {
		capture,
		captureBody,
		createFolder,
		dismissReminder,
		getReminders,
		getVocab,
		CAPTURE_URL,
		NetworkError,
		type Reminder,
		type Vocab
	} from '$lib/trophic/api';
	import { UI_COLORS } from '$lib/trophic/colors';
	import { deviceType, virtualKeyboard } from '$lib/trophic/device.svelte';
	import { browserEnv, enqueue, initRetryQueue, pendingCount } from '$lib/trophic/retry-queue';
	import { validate } from '$lib/trophic/validation';

	// Matches http(s), www., and bare domains — the source's regex, used to
	// refuse links rather than store them.
	const URL_RE =
		/https?:\/\/[^\s]+|www\.[^\s]+|[a-zA-Z0-9][-a-zA-Z0-9]*\.[a-zA-Z]{2,}(?:\/[^\s]*)?/g;

	let draft = $state('');
	let vocab = $state<Vocab | undefined>(undefined);
	let reminders = $state<Reminder[]>([]);
	let input = $state<SmoothTextarea | null>(null);

	let sliding = $state(false);
	let justSent = $state(false);
	let shaking = $state(false);
	let nope = $state(false);
	let typeGlow = $state(0);
	let error = $state<string | null>(null);
	let uiDimmed = $state(false);
	let inputFocused = $state(false);
	let isMobile = $state(false);

	let glowTimer: ReturnType<typeof setTimeout>;
	let dimTimer: ReturnType<typeof setTimeout>;
	let suppressGlow = false;

	// Lines the connection swallowed, waiting to be replayed. The count is
	// shown rather than hidden: the user has to be able to see that a thought
	// is held and not lost, or they will retype it.
	let queued = $state(0);
	const keyboard = virtualKeyboard();

	// Restore the draft the way the source does: sessionStorage, so a reload
	// mid-thought does not eat it, but it does not outlive the session either.
	$effect(() => {
		try {
			draft = sessionStorage.getItem('capture-draft') ?? '';
		} catch {
			/* no sessionStorage; not worth a message */
		}
		isMobile = deviceType().isMobile;
		getVocab().then((v) => (vocab = v));
		// Replay anything the connection ate, now and whenever it comes back.
		queued = pendingCount(browserEnv());
		const stopRetry = initRetryQueue(() => {
			queued = pendingCount(browserEnv());
			getVocab().then((v) => (vocab = v));
		});
		// What has come due while you were away. Fetched once on arrival: this
		// screen is opened to write, not left open to be notified at, and this
		// app does not do notifications on purpose.
		getReminders()
			.then((r) => (reminders = r.reminders))
			.catch(() => {
				/* a missing strip is not worth an error under the capture box */
			});
		// Desktop only — on a phone, focusing here would throw the keyboard up
		// over the screen before the user asked for it.
		const t = isMobile ? undefined : setTimeout(() => input?.focus(), 300);
		return () => {
			if (t) clearTimeout(t);
			stopRetry();
		};
	});

	// Persist and pulse the glow on every keystroke.
	let lastDraft = '';
	$effect(() => {
		if (draft === lastDraft) return;
		lastDraft = draft;
		try {
			sessionStorage.setItem('capture-draft', draft);
		} catch {
			/* ignore */
		}
		if (suppressGlow) return;
		typeGlow = 1;
		clearTimeout(glowTimer);
		glowTimer = setTimeout(() => (typeGlow = 0), 600);
	});

	// Idle dimming. Any mouse movement resets it; the fade back takes 30s, so
	// in practice the chrome stays gone while you are writing.
	$effect(() => {
		function reset() {
			uiDimmed = false;
			clearTimeout(dimTimer);
			dimTimer = setTimeout(() => (uiDimmed = true), 4000);
		}
		reset();
		window.addEventListener('mousemove', reset);
		window.addEventListener('touchstart', reset);
		return () => {
			clearTimeout(dimTimer);
			window.removeEventListener('mousemove', reset);
			window.removeEventListener('touchstart', reset);
		};
	});

	// Live validation. The only thing that can lock the bar, and it can only
	// do it when a `--directive` disagrees with the folder registry — see
	// validation.ts for why nothing else about a draft is checkable.
	const validation = $derived(validate(draft, vocab));
	const blinkIndices = $derived(validation.issues.flatMap((i) => i.blinkIndices));
	const fixable = $derived(validation.issues.find((i) => i.createFolder)?.createFolder);

	async function createMissingFolder() {
		if (!fixable) return;
		try {
			await createFolder(fixable);
			vocab = await getVocab();
			input?.focus();
		} catch (e) {
			error = e instanceof Error ? e.message : 'could not create that folder';
		}
	}

	async function dismiss(reminder: Reminder) {
		// Optimistic: the strip must not sit there while a loopback round-trip
		// happens, or dismissing feels broken.
		reminders = reminders.filter(
			(r) => r.entry_id !== reminder.entry_id || r.line !== reminder.line
		);
		try {
			const r = await dismissReminder(reminder.entry_id, reminder.line);
			reminders = r.reminders;
		} catch {
			reminders = (await getReminders()).reminders;
		}
	}

	function triggerShake() {
		shaking = true;
		setTimeout(() => (shaking = false), 500);
	}

	function flashSent() {
		justSent = true;
		setTimeout(() => (justSent = false), 900);
	}

	async function submit() {
		const text = draft.trim();
		if (!text || sliding) return;

		// A locked draft shakes instead of sending. The message is already on
		// screen and the offending tokens are already blinking, so saying
		// anything more here would be saying it twice.
		if (validation.locked) {
			triggerShake();
			return;
		}

		error = null;
		const snapshot = draft;

		flashSent();
		sliding = true;
		setTimeout(() => {
			draft = '';
			lastDraft = '';
			try {
				sessionStorage.setItem('capture-draft', '');
			} catch {
				/* ignore */
			}
			sliding = false;
			input?.focus();
		}, 220);

		try {
			await capture(text);
			// The vocabulary just grew by whatever was in that line.
			vocab = await getVocab();
		} catch (e) {
			// The two failures are not the same thing. A dead connection is not
			// the user's problem: the line goes into the retry queue and is
			// replayed when the browser comes back, so the draft stays gone and
			// the thought is still kept. A refusal from a server that answered
			// is the user's problem, and it gives the text back — losing a
			// captured thought is the one thing this app cannot do.
			if (e instanceof NetworkError) {
				enqueue(browserEnv(), CAPTURE_URL, captureBody(text));
				queued = pendingCount(browserEnv());
			} else {
				if (!draft) draft = snapshot;
				error = `${e instanceof Error ? e.message : 'failed to save'} — restored your text`;
				triggerShake();
			}
		}
	}

	function handlePaste(e: ClipboardEvent) {
		const text = e.clipboardData?.getData('text/plain') ?? '';
		if (!text || !URL_RE.test(text)) return;
		// Links are refused on purpose: this is a place for your own words. The
		// rest of the paste still lands, so a sentence with a URL in it is not
		// lost, only de-linked.
		e.preventDefault();
		const cleaned = text.replace(URL_RE, '').replace(/\s{2,}/g, ' ').trim();
		if (cleaned) draft = draft + cleaned;
		triggerShake();
		nope = true;
		setTimeout(() => (nope = false), 2000);
	}

	function handleKeyDown(e: KeyboardEvent) {
		if (e.isComposing || e.keyCode === 229) return;
		if (e.key !== 'Enter' || e.shiftKey) return;
		e.preventDefault();

		// Enter is not a keystroke for glow purposes.
		suppressGlow = true;
		setTimeout(() => (suppressGlow = false), 100);

		// The CLI. `--folders` keeps its name from the source even though what
		// it opens here is called the log — it is the same screen: the daily
		// log lives on the folders page there.
		const cmd = draft.trim().toLowerCase();
		if (cmd === '--folders' || cmd === '--log') {
			draft = '';
			goto('/trophic/log');
			return;
		}
		// `--assign` keeps the source's name for the mapping screen; it is one
		// of the tokenizer's nav commands, so it never reads as a directive.
		if (cmd === '--assign') {
			draft = '';
			goto('/trophic/mapping');
			return;
		}
		if (cmd === '--settings') {
			draft = '';
			goto('/settings');
			return;
		}
		if (cmd === '--codex' || cmd === '--logout' || cmd === '--dev') {
			// Recognised by the tokenizer as navigation, so it would never be
			// stored as a directive anyway. Say so rather than swallow it.
			error = `${cmd} has no screen here yet`;
			return;
		}

		submit();
	}

	// Swipe right to send, on touch.
	let touchOrigin: { x: number; y: number } | null = null;
	function onTouchStart(e: TouchEvent) {
		touchOrigin = { x: e.touches[0].clientX, y: e.touches[0].clientY };
	}
	function onTouchEnd(e: TouchEvent) {
		if (!touchOrigin || !isMobile) return;
		const t = e.changedTouches[0];
		const dx = t.clientX - touchOrigin.x;
		const dy = Math.abs(t.clientY - touchOrigin.y);
		touchOrigin = null;
		if (dx < 60 || dy > 40) return; // not a clear rightward swipe
		submit();
	}

	const indicatorFill = $derived(
		justSent ? UI_COLORS.success : shaking ? UI_COLORS.error : UI_COLORS.muted
	);
	// The notch is one filled shape so the top edge stays a single straight
	// line; the trapezoid is cut out of the bottom.
	const NOTCH =
		'M0,0 L600,0 L600,2 L345,2 C342,2 340,13 335,13 L265,13 C260,13 258,2 255,2 L0,2 Z';
</script>

<header
	class="ui-dim sticky top-0 z-40 flex items-center justify-between bg-[#14100c] px-6 py-5 text-[11px] tracking-wide text-stone-500 {uiDimmed
		? 'dimmed'
		: ''}"
>
	<span class="text-stone-300">trophic</span>
	<nav class="flex items-center gap-4">
		<a
			href="/trophic/log"
			class="rounded bg-stone-800 px-2.5 py-1 text-[10px] tracking-wide text-stone-400 transition-colors hover:bg-stone-700 hover:text-stone-200"
		>
			log
		</a>
	</nav>
</header>

<!-- Centred, until the on-screen keyboard takes half the screen: then the box
     goes to the top, because centring inside what is left puts it under the
     keyboard. `useVirtualKeyboard`'s 150px absolute test is what distinguishes
     that from Chrome merely hiding its address bar on scroll. -->
<main
	class="flex flex-1 flex-col items-center px-6 {keyboard.open
		? 'justify-start pt-6 pb-4'
		: 'justify-center pb-24'}"
>
	<div class="flex w-full max-w-xl flex-col gap-3">
		<!-- The reminder strip. Above the box, because it is context for what
		     you are about to write, not a task list to work through. -->
		{#each reminders as reminder (reminder.entry_id + ':' + reminder.line)}
			<div
				class="flex items-baseline justify-between gap-4 rounded border border-stone-800 bg-stone-900/50 px-3 py-2"
				style="animation:landing-fade-in 0.3s ease-out"
			>
				<span class="min-w-0 flex-1 truncate font-mono text-[12px] text-stone-300">
					{reminder.line_text}
				</span>
				<span class="shrink-0 text-[10px] text-stone-500">
					{new Date(reminder.due_at).toLocaleDateString(undefined, {
						month: 'short',
						day: 'numeric'
					})}
				</span>
				<button
					type="button"
					class="shrink-0 text-[10px] text-stone-500 transition-colors hover:text-stone-300"
					onclick={() => dismiss(reminder)}
				>
					dismiss
				</button>
			</div>
		{/each}

		<div
			data-capture-box
			role="group"
			aria-label="capture"
			class="relative overflow-hidden"
			style="touch-action:pan-y"
			ontouchstart={onTouchStart}
			ontouchend={onTouchEnd}
		>
			<!-- `none`, not `translateX(0)`, when it is not moving. An element
			     with a transform becomes the containing block for any `fixed`
			     descendant, and the suggestion panel is one: with an identity
			     transform sitting here it positioned itself against this div
			     instead of the viewport and landed off-screen. The source
			     portals the panel to <body> and never meets this. -->
			<div
				style="transform:{sliding ? 'translateX(110%)' : 'none'};
				       transition:{sliding ? 'transform 220ms ease-in' : 'none'}"
			>
				<div class="trophic-scrollbar-hide overflow-y-auto" style="max-height:40vh">
					<SmoothTextarea
						bind:this={input}
						bind:value={draft}
						{vocab}
						{blinkIndices}
						placeholder="what happened?"
						onkeydown={handleKeyDown}
						onpaste={handlePaste}
						onfocus={() => (inputFocused = true)}
						onblur={() => (inputFocused = false)}
					/>
				</div>
			</div>

			<!-- The indicator line. Its colour is the only feedback the bar
			     gives: grey resting, amber while you type, green for 900ms on
			     send, red plus a damped shake on a refusal. -->
			<svg
				viewBox="0 0 600 14"
				preserveAspectRatio="none"
				class="block h-[14px] w-full"
				style="animation:{shaking ? 'indicator-shake 400ms ease-out' : 'none'}"
			>
				<defs>
					<linearGradient id="type-glow" x1="0" x2="1" y1="0" y2="0">
						<stop offset="0%" stop-color="transparent" />
						<stop offset="5%" stop-color="#f59e0b" stop-opacity="0.3" />
						<stop offset="25%" stop-color="#f59e0b" stop-opacity="0.7" />
						<stop offset="50%" stop-color="#f59e0b" />
						<stop offset="75%" stop-color="#f59e0b" stop-opacity="0.7" />
						<stop offset="95%" stop-color="#f59e0b" stop-opacity="0.3" />
						<stop offset="100%" stop-color="transparent" />
					</linearGradient>
				</defs>
				<path d={NOTCH} fill={indicatorFill} style="transition:fill 0.3s ease" />
				<path
					d={NOTCH}
					fill="url(#type-glow)"
					opacity={typeGlow > 0 && !justSent && !shaking ? 1 : 0}
					style="transition:{typeGlow > 0 ? 'opacity 0.1s ease-in' : 'opacity 0.4s ease-out'}"
				/>
			</svg>
		</div>

		{#if isMobile}
			<SyntaxBar visible={inputFocused} oninsert={(t) => input?.insertText(t)} />
		{/if}

		{#if nope}
			<p class="text-center text-[11px] text-stone-500">Nope</p>
		{/if}

		{#if queued > 0}
			<p class="text-[11px] text-stone-500">
				{queued}
				{queued === 1 ? 'line' : 'lines'} waiting for the connection — they will send themselves
			</p>
		{/if}

		<!-- One issue at a time: the first is the one to fix, and a stack of
		     red text under the capture bar is its own kind of noise. -->
		{#each validation.issues.slice(0, 1) as issue (issue.message)}
			<p class="flex items-baseline gap-2 text-[11px] text-red-400">
				<span>{issue.message}</span>
				{#if issue.createFolder}
					<button
						type="button"
						class="rounded bg-stone-800 px-2 py-0.5 text-[10px] text-stone-300 transition-colors hover:bg-stone-700"
						onclick={createMissingFolder}
					>
						create it
					</button>
				{/if}
			</p>
		{/each}

		{#if error}
			<p class="text-[11px] text-red-400">{error}</p>
		{/if}
	</div>
</main>

{#if !isMobile}
	<footer
		class="ui-dim pointer-events-none fixed right-0 bottom-0 left-0 flex flex-col items-center pt-3 pb-5 {uiDimmed
			? 'dimmed'
			: ''}"
	>
		<p class="text-center text-[11px] leading-relaxed text-stone-500">
			<span style="color:#60a5faaa">&lt;tag&gt;</span>
			<span class="mx-2 text-stone-700">&middot;</span>
			<span style="color:#fb7185aa">\pattern</span>
			<span class="mx-2 text-stone-700">&middot;</span>
			<span>enter to send, tab to choose existing tags</span>
		</p>
	</footer>
{/if}
