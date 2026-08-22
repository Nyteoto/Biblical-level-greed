<script lang="ts">
	/**
	 * The standing strip: one open todo, and the next reminder.
	 *
	 * It is on every screen because both things it carries are promises, and a
	 * promise you only see when you go looking for it is one you have already
	 * broken. That is also why it holds exactly one todo at a time — a list of
	 * ten on every screen is wallpaper, and wallpaper is not read. One is a
	 * thing you either do or deliberately move past.
	 *
	 * ## Which todo
	 *
	 * Oldest first, unless you have queued one. Oldest is the order you would
	 * have to argue against — it is the thing that has been waiting longest —
	 * and queueing is how you argue against it, per device, without writing
	 * anything to the log. See `queued.svelte.ts` for why that is not an event.
	 *
	 * A queued key that matches nothing open is ignored rather than repaired:
	 * the todo was checked off, or its entry is gone, and falling back to oldest
	 * is what you wanted anyway.
	 *
	 * ## Which reminder
	 *
	 * Overdue before upcoming, soonest first within each. A countdown is the
	 * whole point of writing `{14/09}` — the fortnight before it is what you
	 * wanted, not the morning it lands — so this counts down rather than waiting
	 * to go off. Days are counted against the *server's* clock, handed over as
	 * `as_of`, because the log's idea of what day it is comes from one place and
	 * a device with a skewed clock does not get a vote.
	 *
	 * Nothing here dismisses a reminder. Dismissing is a decision with an event
	 * behind it and a home in the journal; this strip is for noticing, and a
	 * control that makes something disappear forever does not belong on a bar
	 * you see on every screen and stop reading by Tuesday.
	 */
	import { goto } from '$app/navigation';
	import { tick as flush } from 'svelte';
	import Glyph from './Glyph.svelte';
	import { banner } from './banner.svelte';
	import { queuedTodo } from './queued.svelte';
	import { uiDim } from './dim.svelte';
	import { toggleLine } from './api';
	import type { BannerReminder, BannerTodo } from './api';

	const bar = banner();

	/**
	 * The strip putting its hand up when a promise has just been written.
	 *
	 * Two short blinks and done. It is the only thing in the app that asks to
	 * be looked at, and it is allowed to because of when it happens: you have
	 * just pressed enter on a line that made a promise, so the strip that keeps
	 * that promise has one moment where it is worth a glance. It does not
	 * repeat and there is nothing to dismiss.
	 *
	 * On the inner row rather than on the strip itself, because the strip's own
	 * opacity belongs to the idle dim and an animation on the same property
	 * would fight it. The capture screen wakes the chrome at the same moment —
	 * see the send handler there — so there is something lit to blink.
	 */
	let landed = $state(false);
	let landedTimer: ReturnType<typeof setTimeout> | undefined;
	let announced = 0;

	$effect(() => {
		const count = bar.landed;
		// Never on the first read: `landed` starts at 0 and this runs on mount.
		if (count === announced) return;
		announced = count;
		clearTimeout(landedTimer);
		landed = false;
		flush().then(() => {
			landed = true;
			landedTimer = setTimeout(() => (landed = false), 1400);
		});
	});

	$effect(() => () => clearTimeout(landedTimer));
	const queue = queuedTodo();
	const dim = uiDim();

	let busy = $state(false);

	const data = $derived(bar.data);

	const current = $derived.by((): BannerTodo | null => {
		const todos = data?.todos ?? [];
		if (todos.length === 0) return null;
		const wanted = queue.key;
		return todos.find((t) => `${t.entry_id}:${t.line}` === wanted) ?? todos[0];
	});

	/** Overdue first, then the countdown — both soonest-first already. */
	const reminder = $derived.by((): BannerReminder | null => {
		const due = data?.due ?? [];
		const soon = data?.upcoming ?? [];
		return due[0] ?? soon[0] ?? null;
	});

	/** Whole days between the server's `as_of` and the due instant, counted on
	 *  calendar days rather than 24-hour blocks: something due tomorrow morning
	 *  reads `1 day left` all of today, which is how a person counts. */
	const daysLeft = $derived.by(() => {
		if (!reminder || !data) return 0;
		const startOfDay = (iso: string) => {
			const d = new Date(iso);
			return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate());
		};
		const ms = startOfDay(reminder.due_at) - startOfDay(data.as_of);
		return Math.round(ms / 86400000);
	});

	const countdown = $derived(
		daysLeft < 0
			? daysLeft === -1
				? 'yesterday'
				: `${Math.abs(daysLeft)} days ago`
			: daysLeft === 0
				? 'today'
				: daysLeft === 1
					? '1 day left'
					: `${daysLeft} days left`
	);

	/** The line without its syntax, short enough to sit on one row. The banner
	 *  is a pointer at something, not a place to read it. */
	const shorten = (raw: string, max = 46) => {
		// `--todo`, `{times}` and `<folders>` are metadata here. The banner has
		// one line to say what the thing is, and where it is filed is not it —
		// the tag is on the entry itself, one click away.
		const clean = raw
			.replace(/--todo\b/g, '')
			.replace(/\{[^}]*\}/g, '')
			.replace(/<[^>]*>/g, '')
			.replace(/\s+/g, ' ')
			.trim();
		return clean.length > max ? clean.slice(0, max - 1).trimEnd() + '…' : clean;
	};

	const albumHref = (item: { folder: string | null; entry_id: string; day?: string }) => {
		const year = (item.day ?? '').slice(0, 4) || 'all';
		return `/folders/${item.folder ?? 'unfiled'}?year=${year}&entry=${item.entry_id}`;
	};

	async function tick() {
		if (!current || busy) return;
		busy = true;
		try {
			await toggleLine(current.entry_id, current.line);
			// The queue pointed at this one; it is done, so the preference is
			// spent. Left behind it would resolve to nothing and quietly do
			// nothing forever.
			if (queue.is(current.entry_id, current.line)) queue.clear();
			await bar.refresh();
		} finally {
			busy = false;
		}
	}

	async function openReminder() {
		if (reminder) await goto(albumHref(reminder));
	}
</script>

{#if current || reminder}
	<div
		class="ui-dim flex shrink-0 flex-wrap items-center gap-x-5 gap-y-2 px-[34px] pt-[18px] text-[13px] {dim.on
			? 'dimmed'
			: ''}"
	>
		{#if current}
			<div class="flex min-w-0 items-center gap-2.5" class:landed>
				<button
					type="button"
					disabled={busy}
					aria-label="check this off"
					title="check this off"
					class="flex h-[17px] w-[17px] shrink-0 items-center justify-center rounded-[5px] border border-neutral-400 transition-colors hover:border-accent-500 disabled:opacity-40"
					onclick={tick}
				>
					<svg
						width="10"
						height="10"
						viewBox="0 0 10 10"
						fill="none"
						stroke="currentColor"
						stroke-width="1.6"
						stroke-linecap="round"
						stroke-linejoin="round"
						class="text-accent-700 opacity-0 transition-opacity hover:opacity-100"
					>
						<path d="M2 5.5 L4 7.5 L8 3" />
					</svg>
				</button>
				<a href={albumHref(current)} class="min-w-0 truncate transition-colors hover:text-neutral-800">
					{shorten(current.text)}
				</a>
				{#if data}
					<!-- The count is the cap doing its job in public. At ten it is the
					     only warning you get before a capture is refused. -->
					<span
						class="flex shrink-0 items-center gap-1.5 tabular-nums {data.open >= data.cap
							? 'text-accent-700'
							: 'text-neutral-600'}"
						title="{data.open} of {data.cap} todos open"
					>
						<Glyph kind="entries" count={data.open} size={12} />
						{data.open}/{data.cap}
					</span>
				{/if}
			</div>
		{/if}

		{#if reminder}
			<button
				type="button"
				class="flex min-w-0 items-center gap-2.5 text-left text-neutral-600 transition-colors hover:text-neutral-800"
				onclick={openReminder}
			>
				<span
					class="shrink-0 rounded-[6px] px-[7px] py-[2px] text-[11px] font-bold tabular-nums {daysLeft <=
					0
						? 'bg-accent-100 text-accent-700'
						: 'bg-neutral-200'}"
				>
					{countdown}
				</span>
				<span class="min-w-0 truncate">{shorten(reminder.line_text)}</span>
			</button>
		{/if}
	</div>
{/if}

<style>
	/* Two blinks. It dips rather than going out — the caret in the capture bar
	   is the thing in this app that goes to nothing, and a second full blink
	   somewhere else would read as the same signal. */
	.landed {
		animation: banner-landed 1400ms ease-out;
	}

	@keyframes banner-landed {
		0% {
			opacity: 0.25;
		}
		12% {
			opacity: 1;
		}
		26% {
			opacity: 0.25;
		}
		40% {
			opacity: 1;
		}
		100% {
			opacity: 1;
		}
	}
</style>
