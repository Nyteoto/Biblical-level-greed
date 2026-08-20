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
	 * The redesign changed the surface and none of the behaviour. It briefly put
	 * the draft in a white card with the deepest shadow on the screen, and that
	 * was wrong: a card is a container, and it made the thought being written
	 * look like an object on the page rather than the page's whole subject. The
	 * source has no card here either — the text sits on the ground with the
	 * notched line under it, and that line is the only edge. Restored, with the
	 * palette from the redesign. Everything above it — the reminder strips, the
	 * attachment chips, the pin — stays a card, because those *are* objects.
	 *
	 * Nothing under the line explains the keys. There was a row reading `tab
	 * takes <has>` and `enter sends · shift+enter is a newline`, and on a screen
	 * whose whole argument is that it holds one thought and nothing else, a
	 * standing instruction is the loudest thing on it. The syntax keys are their
	 * own affordance and stay.
	 *
	 * There is deliberately no feed on this screen. The capture bar is for
	 * getting a thought out of your head; reading them back is the log's job.
	 */
	import { goto } from '$app/navigation';
	import SmoothTextarea from '$lib/trophic/SmoothTextarea.svelte';
	import { banner } from '$lib/trophic/banner.svelte';
	import { uiDim } from '$lib/trophic/dim.svelte';
	import SyntaxBar from '$lib/trophic/SyntaxBar.svelte';
	import TabPill from '$lib/trophic/TabPill.svelte';
	import TodoTally from '$lib/trophic/TodoTally.svelte';
	import {
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
	import { GLOW_STOPS, UI_COLORS, phosphorize } from '$lib/trophic/colors';
	import { deviceType } from '$lib/trophic/device.svelte';
	import { attach, release, type Attachment } from '$lib/trophic/media';
	import { tagForPin, withPinnedTag } from '$lib/trophic/pinned';
	import { pinned } from '$lib/trophic/pinned.svelte';
	import { startUploads } from '$lib/trophic/uploads.svelte';
	import { browserEnv, enqueue, initRetryQueue, pendingCount } from '$lib/trophic/retry-queue';
	import { validate, CAP_WARN_AT, MAX_RAW_LEN } from '$lib/trophic/validation';

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
	// Shared, because the standing banner in the layout fades with this too.
	const dim = uiDim();
	const uiDimmed = $derived(dim.on);
	// Leaving mid-fade would strand the banner invisible on the next screen,
	// where nothing moves the pointer over a capture box to bring it back.
	$effect(() => () => dim.set(false));
	let isMobile = $state(false);

	let glowTimer: ReturnType<typeof setTimeout>;
	let dimTimer: ReturnType<typeof setTimeout>;
	/** The pending optimistic clear of the draft. Held so a refusal arriving
	 *  inside the slide-out can cancel it — see `submit`. */
	let clearTimer: ReturnType<typeof setTimeout> | undefined;
	/** Brings the chrome back and restarts the idle countdown. Assigned by the
	 *  effect below, which is also the only thing that clears the timer. */
	let wake: () => void = () => {};
	let suppressGlow = false;

	// Lines the connection swallowed, waiting to be replayed. The count is
	// shown rather than hidden: the user has to be able to see that a thought
	// is held and not lost, or they will retype it.
	let queued = $state(0);

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
	//
	// `wake` is hoisted out of the effect because the send handler needs it: a
	// captured `--todo` makes the banner announce itself, and announcing into
	// chrome that has faded to nothing is a blink nobody sees.
	$effect(() => {
		function reset() {
			dim.set(false);
			clearTimeout(dimTimer);
			dimTimer = setTimeout(() => dim.set(true), 4000);
		}
		wake = reset;
		reset();
		window.addEventListener('mousemove', reset);
		window.addEventListener('touchstart', reset);
		return () => {
			clearTimeout(dimTimer);
			window.removeEventListener('mousemove', reset);
			window.removeEventListener('touchstart', reset);
		};
	});

	/**
	 * Start typing and it goes in the bar, wherever the focus was.
	 *
	 * The autofocus above cannot be relied on. iPadOS only honours a
	 * programmatic `focus()` inside a user gesture, so on the machine this app
	 * is actually written on — an iPad with a hardware keyboard — the bar
	 * comes up unfocused and the first thing you type goes nowhere. Tapping the
	 * screen to fix it is the exact gesture a keyboard exists to avoid.
	 *
	 * So: a printable key pressed while nothing else is focused *is* the
	 * gesture. The bar takes the focus and the keystroke both.
	 *
	 * The keystroke is inserted by hand rather than left to the browser. After
	 * `focus()` inside a keydown, whether the character reaches the newly
	 * focused element is a question every engine answers differently; typing
	 * the first letter of a thought and watching it vanish is worse than the
	 * small amount of care this takes. `preventDefault` stops the second copy.
	 *
	 * What it deliberately does not catch: anything with a modifier (those are
	 * shortcuts, including the browser's own), anything while a composition is
	 * running (an IME is mid-word and the keystroke is not a character yet),
	 * and anything at all while another field has the focus — the pin's menu,
	 * a name box, the Log's jump field. Non-printable keys only move the focus:
	 * a Backspace or an Enter aimed at an empty bar has nothing to do, and
	 * stealing them would break Escape and Tab everywhere on the screen.
	 */
	$effect(() => {
		function typeAnywhere(event: KeyboardEvent) {
			if (event.metaKey || event.ctrlKey || event.altKey || event.isComposing) return;
			// `key` is one code point for a printable key and a word — `Enter`,
			// `ArrowLeft` — for everything else.
			if ([...event.key].length !== 1) return;
			const active = document.activeElement as HTMLElement | null;
			if (
				active &&
				(active.tagName === 'TEXTAREA' ||
					active.tagName === 'INPUT' ||
					active.isContentEditable)
			) {
				return;
			}
			event.preventDefault();
			input?.focus();
			input?.insertText(event.key);
		}

		window.addEventListener('keydown', typeAnywhere);
		return () => window.removeEventListener('keydown', typeAnywhere);
	});

	// Live validation. It locks the bar when a `--directive` disagrees with the
	// folder registry, and when the draft is longer than a capture may be — see
	// validation.ts for why those two and nothing else about a draft.
	/** The one on screen: soonest due, which is the order the API hands them
	 *  back in. */
	const due = $derived(reminders[0] ?? null);

	// The pin's tag is appended on the way out, so it counts against the cap
	// even though it is nowhere in the box: ` <tag>`, three characters plus the
	// tag. Reserving it here is what stops the bar reporting room the server
	// will then refuse. It over-counts by that much in the one case where the
	// draft already carries the tag and `withPinnedTag` will append nothing —
	// sixty characters out of twenty thousand, and always in the safe
	// direction, which is worth not tokenizing the whole draft again to know.
	const reserved = $derived(pinTag ? pinTag.length + 3 : 0);
	const validation = $derived(validate(draft, vocab, reserved));
	const blinkIndices = $derived(validation.issues.flatMap((i) => i.blinkIndices));
	const fixable = $derived(validation.issues.find((i) => i.createFolder)?.createFolder);

	// How much room is left, and whether to say so. Silent for an ordinary
	// line and for most long ones: a counter standing on this screen all day
	// would be a standing instruction, which is the thing the bar refuses to
	// have. It appears in the last tenth, which is far enough out that there is
	// still time to split the thought in two.
	const used = $derived(draft.trim() ? draft.trim().length + reserved : 0);
	const remaining = $derived(MAX_RAW_LEN - used);
	// Not once the draft is over: past that point the refusal under the line
	// states the same fact in the place that can also say what to do about it,
	// and two figures saying one thing is the noise this app deletes.
	const showCount = $derived(used >= CAP_WARN_AT && remaining >= 0);

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

	/**
	 * Give a refused capture back, whole.
	 *
	 * This is the one thing this app is not allowed to get wrong. A capture the
	 * server declines is not a capture the user is finished with, so the text
	 * goes back in the box, the files go back on it, and the session copy is
	 * rewritten so a reload finds it too. `lastDraft` is set alongside because
	 * the persistence effect skips a draft it has already seen, and a restore
	 * that leaves an empty string in sessionStorage is a restore that a refresh
	 * undoes.
	 */
	function restoreDraft(text: string, files: Attachment[]) {
		if (clearTimer) {
			clearTimeout(clearTimer);
			clearTimer = undefined;
		}
		sliding = false;
		draft = text;
		lastDraft = text;
		attachments = files;
		try {
			sessionStorage.setItem('capture-draft', text);
		} catch {
			/* ignore */
		}
		input?.focus();
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
		// Held, because a refusal has to be able to cancel it. The draft is
		// cleared optimistically at the end of the slide-out — that is what
		// makes the bar feel instant — but the server can answer in less than
		// the 220ms that takes. Cancelling the timer is what stops the answer
		// and the clear from racing: without it a refusal restored the text
		// into a box this callback then emptied, and the thought was gone with
		// nothing on screen to say where it went. That happened.
		clearTimer = setTimeout(() => {
			clearTimer = undefined;
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
			// The folder as the line was written: the pinned one, else the first
			// `<tag>` in it. Filename only — membership is still resolved.
			if (sent.length > 0) startUploads(entry.id, sent, entry.folders?.[0] ?? '');
			// A line carrying a `--todo` changes what the banner says and how
			// much room is left under the cap. Cheap, and only on a real send.
			if (entry.todo_lines.length > 0) {
				// And the strip says so. The refresh is what makes it true; the
				// announcement is what makes it noticed, and the wake is what
				// makes it visible — four seconds of typing will have faded the
				// chrome out from under it.
				wake();
				banner()
					.refresh()
					.then(() => banner().announce());
			}
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
				// A refusal from a server that answered. Put everything back —
				// the text, the files that were going with it, and the copy in
				// sessionStorage that a reload would read. Unconditionally, and
				// whether or not the clear has already run: the draft on screen
				// at this moment is either still the snapshot or already empty,
				// and in both cases the snapshot is what belongs there.
				restoreDraft(snapshot, sent);
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
		// it opens here is called the log — it is the same screen.
		const cmd = draft.trim().toLowerCase();
		if (cmd === '--folders' || cmd === '--log') {
			draft = '';
			goto('/log');
			return;
		}
		// `--assign` keeps the source's name for the mapping screen, which the
		// redesign made a page hanging off Settings rather than a tab of its own.
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
	// line; the trapezoid is cut out of the bottom. Kept to the pixel — the
	// redesign changes what colour it is and nothing about what it is.
	const NOTCH =
		'M0,0 L600,0 L600,2 L345,2 C342,2 340,13 335,13 L265,13 C260,13 258,2 255,2 L0,2 Z';
</script>

<svelte:window onclick={() => (pinMenu = false)} />

<!-- The header holds the whole of the app's navigation on the left and the pin
     on the right, and nothing else. The wordmark went when capture took the
     root: this screen is at its best with nothing on it but the line being
     written, and both of these fade out under the idle dim while you write. -->
<header
	class="ui-dim flex shrink-0 items-center justify-between px-[34px] pt-[22px] {uiDimmed
		? 'dimmed'
		: ''}"
>
	<TabPill />

	<div class="relative">
		<button
			type="button"
			class="lift lift-sm flex items-center gap-[9px] rounded-[10px] bg-surface px-[13px] py-2 shadow-sm"
			onclick={(e) => {
				e.stopPropagation();
				pinMenu = !pinMenu;
			}}
		>
			{#if pinnedFolder}
				<span class="h-2 w-2 rounded-full" style="background:{phosphorize(pinnedFolder.color)}"></span>
				<span class="text-[13px] font-semibold">{pinnedFolder.name}</span>
				<span class="text-[11px] text-neutral-700">
					pinned ·
					<!-- Unpinning is one word inside the pill rather than a second
					     control: the pill is only on screen when something is
					     pinned, so the two are never ambiguous. -->
					<span
						role="button"
						tabindex="0"
						class="hover:text-accent-700"
						onclick={(e) => {
							e.stopPropagation();
							pin.set(null);
							pinMenu = false;
						}}
						onkeydown={(e) => {
							if (e.key === 'Enter' || e.key === ' ') {
								e.preventDefault();
								e.stopPropagation();
								pin.set(null);
							}
						}}>unpin</span
					>
				</span>
			{:else}
				<span class="h-2 w-2 rounded-full bg-neutral-400"></span>
				<span class="text-[13px] font-semibold text-neutral-700">pin a folder</span>
			{/if}
		</button>

		{#if pinMenu}
			<div
				class="absolute top-full right-0 z-50 mt-2 flex max-h-[60vh] min-w-[190px] flex-col overflow-y-auto rounded-[12px] bg-surface p-1.5 shadow-lg"
				style="animation:landing-fade-in 0.15s ease-out"
			>
				{#each folders as f (f.id)}
					{@const tag = tagForPin(f)}
					<button
						type="button"
						class="flex items-center gap-2.5 rounded-lg px-3 py-2 text-left text-[13px] transition-colors hover:bg-neutral-200 disabled:opacity-50 disabled:hover:bg-transparent"
						disabled={!tag}
						title={tag ? `captures land as <${tag}>` : 'no tag points at this folder'}
						onclick={() => {
							pin.set(f.id);
							pinMenu = false;
						}}
					>
						<span class="h-2 w-2 shrink-0 rounded-full" style="background:{f.color}"></span>
						<span class="truncate {f.id === pin.id ? 'font-bold' : ''}">{f.name}</span>
					</button>
				{:else}
					<span class="px-3 py-2 text-[13px] text-neutral-700">no folders yet</span>
				{/each}
			</div>
		{/if}
	</div>
</header>

<!-- Centred, and it stays centred when the keyboard opens.
     This once switched to `justify-start` on `keyboard.open`, which snapped
     the bar to the top of the screen the instant you tapped it. The source
     does not reflow here and neither should this: Safari scrolls a focused
     input into view on its own, and a layout that jumps under your thumb is
     worse than one that sits a little high. -->
<main class="flex min-h-0 flex-1 flex-col items-center justify-center px-[30px]">
	<div class="flex w-full max-w-[720px] flex-col gap-4">
		<!-- The reminder strip. Above the box, because it is context for what
		     you are about to write, not a task list to work through — and
		     **one** strip, never a list, which is the same argument made in the
		     layout. The source renders a single `activeReminder`
		     (`CaptureClient.tsx:118`); this rendered every due line, and a
		     corpus with two years in it turned the capture screen into seventy
		     stacked cards with the writing box pushed off the bottom. Dismissing
		     the top one brings up the next. -->
		{#if due}
			<div
				class="flex items-baseline gap-4 rounded-[12px] bg-surface px-4 py-3 shadow-sm"
				style="animation:landing-fade-in 0.3s ease-out"
			>
				<span class="min-w-0 flex-1 truncate font-mono text-[13px]">
					{due.line_text}
				</span>
				{#if reminders.length > 1}
					<!-- Said rather than hidden. One strip is the shape; a person who
					     has been away for a month still has to be able to tell that
					     there is a queue behind it. -->
					<span class="shrink-0 text-[11px] text-neutral-700">
						+{reminders.length - 1} more
					</span>
				{/if}
				<span class="shrink-0 text-[11px] text-neutral-700">
					{new Date(due.due_at).toLocaleDateString(undefined, {
						month: 'short',
						day: 'numeric'
					})}
				</span>
				<button
					type="button"
					class="shrink-0 text-[11px] font-semibold text-neutral-700 transition-colors hover:text-accent-700"
					onclick={() => dismiss(due)}
				>
					dismiss
				</button>
			</div>
		{/if}

		<!-- What is about to go with the line. Nothing is uploaded until send,
		     so removing a chip costs nothing and a long clip is not sent twice
		     because the text was edited after picking it. -->
		{#if attachments.length > 0}
			<div class="flex flex-wrap gap-2.5">
				{#each attachments as item (item.key)}
					<div
						class="relative h-[74px] w-[74px] overflow-hidden rounded-[12px] bg-neutral-200 shadow-sm"
					>
						{#if item.kind === 'image'}
							<img src={item.preview} alt="" class="h-full w-full object-cover" />
						{:else}
							<!-- svelte-ignore a11y_media_has_caption -->
							<video src={item.preview} muted playsinline class="h-full w-full object-cover"
							></video>
							<span
								class="absolute bottom-1.5 left-1.5 rounded-[5px] bg-ground/85 px-[5px] py-[2px] font-mono text-[9px] text-neutral-800"
							>
								clip
							</span>
						{/if}

						<button
							type="button"
							class="absolute top-[5px] right-[5px] flex h-[19px] w-[19px] items-center justify-center rounded-full bg-ground/90 text-[12px] leading-none text-neutral-800 shadow-sm transition-colors hover:text-accent"
							aria-label="remove"
							onclick={() => drop(item.key)}>×</button
						>
					</div>
				{/each}
			</div>
		{/if}

		<!-- The writing surface: no surface. The draft is on the page ground and
		     the notched line is the only edge it has, which is the source's
		     arrangement and the reason the bar reads as a place to think rather
		     than a field to fill in. `overflow:hidden` stays — it is what clips
		     the draft as it slides out on send. -->
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
						onkeydown={handleKeyDown}
						onpaste={handlePaste}
					/>
				</div>
			</div>

			<!-- The attach button, in the right padding `.smooth-layout` already
			     reserves, and on the baseline of the first line of the draft. A
			     sibling of the slide-out wrapper, not a child: inside it, it
			     would slide away with the draft on send. -->
			<label
				class="absolute top-[13px] right-0 cursor-pointer p-1 text-neutral-600 transition-colors hover:text-ink"
				title="attach a photo or a clip"
			>
				<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor"
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
			     gives: grey resting, the accent gradient while you type, green
			     for 900ms on send, red plus a damped shake on a refusal. -->
			<svg
				viewBox="0 0 600 14"
				preserveAspectRatio="none"
				class="block h-[14px] w-full"
				style="animation:{shaking ? 'indicator-shake 400ms ease-out' : 'none'}"
			>
				<defs>
					<linearGradient id="type-glow" x1="0" x2="1" y1="0" y2="0">
						{#each GLOW_STOPS as stop (stop.offset)}
							<stop offset={stop.offset} stop-color={stop.color} stop-opacity={stop.opacity} />
						{/each}
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

		<!-- How much room is left, and only near the end of it. It is a gauge
		     rather than a message, so it sits at the end of the line instead of
		     in the stack of messages below, and it is the one grey figure here:
		     the accent is the refusal's, and a counter that turns red before
		     anything has been refused is the app nagging. -->
		{#if showCount}
			<p class="-mt-1 text-right font-mono text-[11px] text-neutral-600">
				{remaining.toLocaleString()} characters left
			</p>
		{/if}

		<!-- The syntax keys. The only standing thing under the line, and they do
		     something rather than say something. -->
		<SyntaxBar oninsert={(t) => input?.insertText(t)} />

		{#if nope}
			<!-- A refusal, so it takes the colour every other refusal in the app
			     takes. It was grey, which made the one message the bar prints when
			     it has just *declined* to keep something look like a footnote. -->
			<p class="text-[12px] text-accent-700">Nope</p>
		{/if}

		{#if queued > 0}
			<p class="text-[12px] text-neutral-700">
				{queued}
				{queued === 1 ? 'line' : 'lines'} waiting for the connection — they will send themselves
			</p>
		{/if}

		<!-- One issue at a time: the first is the one to fix, and a stack of
		     red text under the capture bar is its own kind of noise. Never a
		     red field — the tokens in the draft are already blinking. -->
		{#each validation.issues.slice(0, 1) as issue (issue.message)}
			<p class="flex items-baseline gap-3 text-[12px] text-accent-700">
				<span>{issue.message}</span>
				{#if issue.createFolder}
					<button
						type="button"
						class="lift lift-sm rounded-lg bg-surface px-2.5 py-1 text-[12px] font-semibold text-ink shadow-sm"
						onclick={createMissingFolder}
					>
						create it
					</button>
				{/if}
			</p>
		{/each}

		{#if error}
			<p class="text-[12px] text-accent-700">{error}</p>
		{/if}
	</div>
</main>

<!-- The column above is vertically centred in whatever is left, so the page
     needs a foot of the same height as the header to centre against.

     The tally stands in it rather than being fixed to the viewport, and that is
     what keeps it out of the way: the foot is reserved space, so a short screen
     with the keyboard up moves the badge instead of putting it under the
     writing. It is the one thing here that does not fade under the idle dim —
     see the note in `TodoTally`, which is where the argument for that lives. -->
<div class="relative h-[62px] shrink-0">
	<TodoTally />
</div>
