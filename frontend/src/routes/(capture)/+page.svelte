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
		attachMedia,
		capture,
		captureBody,
		createFolder,
		dismissReminder,
		getFolders,
		getReminders,
		getVocab,
		CAPTURE_URL,
		NetworkError,
		type Folder,
		type Reminder,
		type Vocab
	} from '$lib/trophic/api';
	import { UI_COLORS } from '$lib/trophic/colors';
	import { deviceType, virtualKeyboard } from '$lib/trophic/device.svelte';
	import { attach, release, type Attachment } from '$lib/trophic/media';
	import { tagForPin, withPinnedTag } from '$lib/trophic/pinned';
	import { pinned } from '$lib/trophic/pinned.svelte';
	import { startUploads } from '$lib/trophic/uploads.svelte';
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

	// Files chosen but not yet sent. They upload on send, not on pick, so a
	// change of mind costs nothing and a five-minute video is not uploaded
	// twice because the line was edited.
	let attachments = $state<Attachment[]>([]);

	// The pin. A folder held here claims every capture until it is let go, so
	// the common case — a run of entries about one thing — costs one tap
	// instead of a tag per line. What it actually does is append the folder's
	// tag to the text on the way out; see pinned.ts for why that, and not a
	// folder id sent alongside.
	let folders = $state<Folder[]>([]);
	let pinMenu = $state(false);
	const pin = pinned();
	const pinnedFolder = $derived(folders.find((f) => f.id === pin.id) ?? null);
	const pinTag = $derived(pinnedFolder ? tagForPin(pinnedFolder) : null);
	// Files still going up live in `uploads.svelte.ts`, not here: a clip takes
	// minutes and you will navigate away while it runs, so its progress bar
	// belongs to the shell.

	function addFiles(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		for (const file of Array.from(input.files ?? [])) {
			const item = attach(file);
			if (item) attachments = [...attachments, item];
			else error = `${file.name} is not a kind of file this keeps`;
		}
		input.value = ''; // so the same file can be picked again after removing it
	}

	function drop(key: string) {
		const going = attachments.find((a) => a.key === key);
		if (going) release(going);
		attachments = attachments.filter((a) => a.key !== key);
	}

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
		getFolders()
			.then((f) => (folders = f.folders))
			.catch(() => {
				/* the pin is a convenience; the bar works without it */
			});
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
		// A clip is a capture on its own, so media alone is enough to send.
		if ((!text && attachments.length === 0) || sliding) return;

		// A locked draft shakes instead of sending. The message is already on
		// screen and the offending tokens are already blinking, so saying
		// anything more here would be saying it twice.
		if (validation.locked) {
			triggerShake();
			return;
		}

		error = null;

		const snapshot = draft;
		// The files go up *after* the entry, in the background. The line is the
		// thought and it is sent the moment you press enter; a clip can take
		// minutes and must never hold that up. Each upload appends itself to
		// the entry as it lands, and the log picks them up when it reads.
		const sent = attachments;

		flashSent();
		sliding = true;
		setTimeout(() => {
			draft = '';
			lastDraft = '';
			attachments = [];
			try {
				sessionStorage.setItem('capture-draft', '');
			} catch {
				/* ignore */
			}
			sliding = false;
			input?.focus();
		}, 220);

		// The pin's tag goes in here, at the last moment, so what is stored is a
		// line that reads exactly as if it had been typed with the tag on it.
		const line = pinTag ? withPinnedTag(text, pinTag) : text;

		try {
			const { entry } = await capture(line);
			// The vocabulary just grew by whatever was in that line.
			vocab = await getVocab();
			if (sent.length > 0) startUploads(entry.id, sent);
		} catch (e) {
			// The two failures are not the same thing. A dead connection is not
			// the user's problem: the line goes into the retry queue and is
			// replayed when the browser comes back, so the draft stays gone and
			// the thought is still kept. A refusal from a server that answered
			// is the user's problem, and it gives the text back — losing a
			// captured thought is the one thing this app cannot do.
			if (e instanceof NetworkError) {
				enqueue(browserEnv(), CAPTURE_URL, captureBody(line));
				queued = pendingCount(browserEnv());
				// The files have nowhere to go: there is no entry id yet, and
				// the queue replays a body, not an upload. Give them back.
				if (sent.length > 0) {
					sent.forEach(release);
					error = `offline — the line is queued, but ${sent.length} file${
						sent.length === 1 ? '' : 's'
					} could not be sent. Attach again when you are back.`;
				}
			} else {
				if (!draft) draft = snapshot;
				sent.forEach(release);
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
			goto('/log');
			return;
		}
		// `--assign` keeps the source's name for the mapping screen; it is one
		// of the tokenizer's nav commands, so it never reads as a directive.
		if (cmd === '--assign') {
			draft = '';
			goto('/mapping');
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

<svelte:window onclick={() => (pinMenu = false)} />

<header
	class="ui-dim sticky top-0 z-40 flex items-center justify-between bg-[#14100c] px-6 py-5 text-[11px] tracking-wide text-stone-500 {uiDimmed
		? 'dimmed'
		: ''}"
>
	<!-- Almost empty on purpose. The wordmark went when capture took the root:
	     the tab bar already says where you are, and this screen is at its best
	     with nothing on it but the line you are writing.
	     The pin sits here rather than beside the attach button, which is the
	     other place it could go: that button lives in the 40px of right padding
	     the text area reserves, and a folder name does not fit in 40px. Up here
	     it also inherits the idle dim, so it fades out while you write and is
	     back the moment you move. -->
	<div class="relative">
		<button
			type="button"
			class="flex items-center gap-1.5 transition-colors hover:text-stone-300"
			onclick={(e) => {
				e.stopPropagation();
				pinMenu = !pinMenu;
			}}
		>
			{#if pinnedFolder}
				<span class="h-1.5 w-1.5 rounded-full" style="background:{pinnedFolder.color}"></span>
				<span style="color:{pinnedFolder.color}">{pinnedFolder.name}</span>
			{:else}
				<span class="text-stone-600">pin a folder</span>
			{/if}
		</button>

		{#if pinMenu}
			<div
				class="absolute top-full left-0 z-50 mt-2 flex max-h-[60vh] min-w-[170px] flex-col overflow-y-auto rounded border border-stone-700 bg-[#1b1613] py-1.5 shadow-xl"
			>
				{#if pin.id}
					<button
						type="button"
						class="px-4 py-2 text-left text-[12px] text-stone-400 transition-colors hover:bg-stone-800 hover:text-stone-200"
						onclick={() => {
							pin.set(null);
							pinMenu = false;
						}}
					>
						unpin
					</button>
				{/if}
				{#each folders as f (f.id)}
					{@const tag = tagForPin(f)}
					<button
						type="button"
						class="flex items-center gap-2 px-4 py-2 text-left text-[12px] transition-colors hover:bg-stone-800 disabled:opacity-30"
						disabled={!tag}
						title={tag ? `captures land as <${tag}>` : 'no tag points at this folder'}
						onclick={() => {
							pin.set(f.id);
							pinMenu = false;
						}}
					>
						<span class="h-1.5 w-1.5 shrink-0 rounded-full" style="background:{f.color}"></span>
						<span class="truncate" style="color:{f.id === pin.id ? f.color : '#d6d3d1'}">
							{f.name}
						</span>
					</button>
				{:else}
					<span class="px-4 py-2 text-[12px] text-stone-500">no folders yet</span>
				{/each}
			</div>
		{/if}
	</div>
	<span></span>
</header>

<!-- Centred, and it stays centred when the keyboard opens.
     This once switched to `justify-start` on `keyboard.open`, which snapped
     the bar to the top of the screen the instant you tapped it. The source
     does not reflow here and neither should this: Safari scrolls a focused
     input into view on its own, and a layout that jumps under your thumb is
     worse than one that sits a little high. `keyboard.open` earns its keep
     one place only — the syntax keys below. -->
<main class="flex flex-1 flex-col items-center justify-center px-6 pb-24">
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

		<!-- What is about to go with the line. Nothing is uploaded until send,
		     so removing a chip costs nothing and a long clip is not sent twice
		     because the text was edited after picking it. -->
		{#if attachments.length > 0}
			<div class="flex flex-wrap gap-2">
				{#each attachments as item (item.key)}
					<div
						class="relative h-16 w-16 overflow-hidden rounded border border-stone-800 bg-stone-900"
					>
						{#if item.kind === 'image'}
							<img src={item.preview} alt="" class="h-full w-full object-cover" />
						{:else}
							<!-- svelte-ignore a11y_media_has_caption -->
							<video src={item.preview} muted playsinline class="h-full w-full object-cover"
							></video>
							<span class="absolute bottom-0.5 left-1 text-[9px] text-stone-300">clip</span>
						{/if}

						<button
							type="button"
							class="absolute top-0 right-0 bg-black/60 px-1 text-[10px] text-stone-300 hover:text-red-400"
							aria-label="remove"
							onclick={() => drop(item.key)}>×</button
						>
					</div>
				{/each}
			</div>
		{/if}

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

			<!-- The attach button, in the 40px of right padding `.smooth-layout`
			     already reserves. A sibling of the slide-out wrapper, not a
			     child: inside it, it would slide away with the draft on send. -->
			<label
				class="absolute top-2 right-0 cursor-pointer p-2 text-stone-600 transition-colors hover:text-stone-300"
				title="attach a photo or a clip"
			>
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
					stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
					<path d="M21.44 11.05 12.25 20.24a5.5 5.5 0 0 1-7.78-7.78l9.19-9.19a3.67 3.67 0 1 1 5.18 5.18l-9.2 9.2a1.83 1.83 0 1 1-2.59-2.6l8.49-8.48" />
				</svg>
				<span class="sr-only">attach a photo or a clip</span>
				<input
					type="file"
					accept="image/*,video/*"
					multiple
					class="hidden"
					onchange={addFiles}
				/>
			</label>

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

		<!-- OR'd, as the source has it: visualViewport detection misses iPad
		     split and floating keyboards, and focus alone misses the case where
		     the keyboard is up but focus has moved to a suggestion. -->
		{#if isMobile}
			<SyntaxBar
				visible={keyboard.open || inputFocused}
				oninsert={(t) => input?.insertText(t)}
			/>
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
