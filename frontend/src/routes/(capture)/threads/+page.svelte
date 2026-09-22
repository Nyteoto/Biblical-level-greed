<script lang="ts">
	/**
	 * Threads — a deadline you kept carrying.
	 *
	 * ## What a thread is, and why it is this narrow
	 *
	 * A `{}` whose reply sets the next `{}`. You write `{fri} finish the intro`;
	 * Friday comes; you answer it with a reply that names the next date. **The
	 * hop is what makes a thread** — a prompt nobody answered is a reminder and
	 * the banner already has it, and a reply carrying no date of its own is an
	 * answer rather than a deadline being moved.
	 *
	 * That last one is still drawn, as the turn that *closed* the chain. A
	 * thread that simply stopped having anything pending, with nothing saying
	 * why, reads as one you walked away from.
	 *
	 * ## The gap is the thing
	 *
	 * Two dates side by side say when; the number between them says how long
	 * you carried it. That is the whole reason this screen is a spine and not a
	 * list — eleven days between the second turn and the third is a fact about
	 * the work that neither date states on its own.
	 *
	 * ## No year, and it says so
	 *
	 * The one lens the scope's year does not cut. A thread routinely crosses
	 * one — you answer in February what you asked in November — and the reading
	 * lens already hands the year back before following a reply for exactly
	 * this reason. The folder still filters, and it matches *any* turn, so a
	 * reply tagged elsewhere cannot make a thread vanish from the folder you
	 * would look for it in.
	 *
	 * ## Answering is still the capture bar's
	 *
	 * There is no reply button here. `--reply` answers the oldest prompt that
	 * has come due, resolved on the server so the client cannot disagree with
	 * it — which means a screen offering to answer *this* one would be making a
	 * promise the write does not keep. Pressing a turn takes you to it in the
	 * reading lens; answering is done where writing is done.
	 */
	import { page } from '$app/state';
	import { getThreads, toggleLine, type Thread, type Turn } from '$lib/trophic/api';
	import { lensHref, readScope } from '$lib/trophic/scope';
	import { lens } from '$lib/trophic/lens.svelte';
	import { banner } from '$lib/trophic/banner-state.svelte';
	import { dayLabel } from '$lib/trophic/log';
	import ColorizedText from '$lib/trophic/ColorizedText.svelte';
	import TodoEntryText from '$lib/trophic/TodoEntryText.svelte';
	import Glyph from '$lib/trophic/Glyph.svelte';

	const scope = $derived(readScope(page.url));

	/** **The folder alone.** The year is in the scope and is deliberately not
	 *  in this key — see the header: half a conversation is not a smaller
	 *  answer, it is a wrong one, so this lens is the one the year does not
	 *  cut. `?? ''` rather than the raw null, because the key is a string. */
	const view = lens(
		() => scope.folder ?? '',
		async () => (await getThreads(scope.folder)).threads,
		[] as Thread[]
	);

	const threads = $derived(view.data);

	/** Live first and soonest first, so the late ones head the screen. */
	const live = $derived(
		threads
			.filter((t) => !t.closed)
			.sort((a, b) => (a.due_at ?? '').localeCompare(b.due_at ?? ''))
	);
	/** Then what finished, by when it finished. */
	const closed = $derived(
		threads
			.filter((t) => t.closed)
			.sort((a, b) => last(b).ts.localeCompare(last(a).ts))
	);

	const last = (thread: Thread) => thread.turns[thread.turns.length - 1];

	/** How long between two turns. Days up to a fortnight, then weeks, then
	 *  months — the resolution you would say it in out loud. A gap under a day
	 *  is nothing worth printing: you answered it the same day. */
	function gap(before: string, after: string): string {
		const days = Math.round(
			(new Date(after).getTime() - new Date(before).getTime()) / 86400000
		);
		if (days < 1) return '';
		if (days <= 14) return `${days}d`;
		if (days <= 70) return `${Math.round(days / 7)}w`;
		return `${Math.round(days / 30)}mo`;
	}

	/** What the standing date says now. The only clock on this screen — the
	 *  server sends an absolute `due_at` and leaves "late" to the reader. */
	function countdown(due: string): { text: string; late: boolean } {
		const days = Math.round((new Date(due).getTime() - Date.now()) / 86400000);
		if (days < 0) return { text: `${-days}d late`, late: true };
		if (days === 0) return { text: 'today', late: true };
		if (days === 1) return { text: 'tomorrow', late: false };
		return { text: `in ${days}d`, late: false };
	}

	/** Where to go to be looking at this turn. The turn's own day decides the
	 *  year, not the scope's: a 2025 turn opens 2025's album. */
	const at = (thread: Thread, turn: Turn) =>
		lensHref(
			'/log',
			{ folder: thread.folder ?? 'unfiled', year: turn.day.slice(0, 4) },
			{ entry: turn.entry_id }
		);

	async function tick(turn: Turn, line: number) {
		try {
			const { entry } = await toggleLine(turn.entry_id, line);
			turn.todo_done = entry.todo_done;
			// Ticking here changes what the strip has to say about the cap.
			banner().refresh();
		} catch (e) {
			view.fail(e);
		}
	}
</script>

<div class="flex min-h-0 flex-1 flex-col overflow-y-auto px-4 pt-[22px] pb-10 sm:px-8">
	<div class="flex shrink-0 flex-wrap items-baseline gap-x-4 gap-y-1">
		<h1 class="text-[34px] leading-none font-extrabold tracking-[-0.03em] text-neutral-800">
			Threads
		</h1>
		<span class="text-[12px] text-neutral-600 tabular-nums">
			{live.length} live · {closed.length} closed
		</span>
		<!-- Said once, because a 2025 turn under a 2026 scope otherwise reads as
		     a bug rather than as the point. -->
		<span class="text-[12px] text-neutral-600">every year</span>
	</div>

	{#if view.error}
		<p class="mt-4 shrink-0 text-[13px] text-error">{view.error}</p>
	{/if}

	{#snippet spine(thread: Thread)}
		<!-- Capped, like the sheet on the reading lens. A turn's date belongs to
		     its text, and on a desk monitor an uncapped row puts the two a hand's
		     width apart — which stops them reading as one thing. -->
		<article
			class="flex max-w-[860px] flex-col py-1"
			style="box-shadow:inset 1px 0 0 0 var(--color-neutral-400)"
		>
			{#each thread.turns as turn, i (turn.entry_id)}
				{@const step = i === 0 ? '' : gap(thread.turns[i - 1].ts, turn.ts)}
				<div class="flex gap-3 pr-2 pl-4 sm:gap-4">
					<!-- The gap, in the gutter the rule runs down. Blank on the first
					     turn: nothing came before it to be a gap from. -->
					<span
						class="w-[34px] shrink-0 pt-[9px] text-right text-[11px] text-neutral-600 tabular-nums"
					>
						{step}
					</span>
					<div class="flex min-w-0 flex-1 gap-3 py-2">
						{#if turn.todo_lines.length > 0}
							<!-- A turn is an entry, so its promises are tickable where they
							     are. The same component and the same call the reading lens
							     uses — there is one checkbox in this app. -->
							<div class="min-w-0 flex-1 text-[15px] leading-[1.55] font-light">
								<TodoEntryText
									entry={{
										clean_text: turn.text,
										todo_lines: turn.todo_lines,
										todo_done: turn.todo_done
									}}
									ontoggle={(line) => tick(turn, line)}
								/>
							</div>
						{:else}
							<p class="m-0 min-w-0 flex-1 text-[15px] leading-[1.55] font-light">
								<ColorizedText text={turn.text} />
							</p>
						{/if}

						{#if turn.media}
							<span class="flex shrink-0 items-center gap-1.5 pt-1 text-[11px] text-neutral-600">
								<Glyph kind="media" count={turn.media} size={12} />{turn.media}
							</span>
						{/if}

						<!-- The way into the reading lens, and the row's only link — the
						     text beside it cannot be one, because a turn carrying todos has
						     buttons in it and an anchor around a button is not a thing.
						     Padded rather than bare: on the tablet this is read on there is
						     no hover, so the date has to be a target you can hit rather than
						     a word that happens to be pressable. -->
						<a
							href={at(thread, turn)}
							class="-my-2 -mr-2 shrink-0 px-2 py-2 text-[11px] text-neutral-600 tabular-nums transition-colors hover:text-ink"
							title="read this day"
						>
							{dayLabel(turn.day)}
						</a>
					</div>
				</div>
			{/each}

			{#if thread.due_at}
				{@const now = countdown(thread.due_at)}
				<!-- The one thing on the spine that is not a turn: the date still
				     standing, under the turn that set it. -->
				<div class="flex gap-3 pr-2 pb-1 pl-4 sm:gap-4">
					<span class="w-[34px] shrink-0"></span>
					<span
						class="text-[11px] tracking-[0.04em] {now.late
							? 'font-bold text-ink'
							: 'text-neutral-700'}"
					>
						{now.text}
					</span>
				</div>
			{/if}
		</article>
	{/snippet}

	{#if view.loading && threads.length === 0}
		<p class="mt-10 text-[13px] text-neutral-600">Reading…</p>
	{:else if threads.length === 0}
		<p class="mt-10 text-[13px] text-neutral-600">No threads.</p>
	{:else}
		{#if live.length}
			<section class="mt-9 flex shrink-0 flex-col gap-5">
				<h2 class="text-[10px] font-bold tracking-[0.18em] text-neutral-600 uppercase">
					Live · {live.length}
				</h2>
				{#each live as thread (thread.id)}
					{@render spine(thread)}
				{/each}
			</section>
		{/if}

		{#if closed.length}
			<section class="mt-11 flex shrink-0 flex-col gap-5">
				<h2 class="text-[10px] font-bold tracking-[0.18em] text-neutral-600 uppercase">
					Closed · {closed.length}
				</h2>
				{#each closed as thread (thread.id)}
					{@render spine(thread)}
				{/each}
			</section>
		{/if}
	{/if}
</div>
