<script lang="ts">
	/**
	 * The manual, rewritten for Trophic.
	 *
	 * It used to describe the tech tree's node kinds, domain shapes and
	 * seasons. Those screens are hidden and this page is reached from Settings,
	 * whose card promises "what the syntax does, and why the log is
	 * append-only" — so that is what it says now.
	 *
	 * Deliberately static: no fetch, no state, nothing that can be out of date
	 * with the server. Everything here is a claim about design, and every rule
	 * below exists because a specific way of keeping a journal was found to
	 * lose things.
	 */
	import { SYNTAX_COLORS } from '$lib/trophic/colors';

	const syntax = [
		{
			glyph: '<folder>',
			color: SYNTAX_COLORS.folder,
			name: 'a pointer',
			body: 'Says what this line is about. A tag is a real thing the moment you type it — nothing has to exist first, and a tag no folder has claimed is not a mistake, it is how tags start.'
		},
		{
			glyph: '{2d}',
			color: SYNTAX_COLORS.time,
			name: 'a time link',
			body: 'Comes back to you when it is due. `{2d}`, `{friday}`, `{03/04}`. The date is worked out from the day you wrote the line, so a rebuild reproduces every reminder exactly.'
		},
		{
			glyph: '\\pattern',
			color: SYNTAX_COLORS.pattern,
			name: 'a pattern',
			body: 'How it went, in your own word. `\\win`, `\\stuck`, `\\steady`. They are counted on Record, and never interpreted — nothing here will tell you what your week meant.'
		},
		{
			glyph: '@place',
			color: SYNTAX_COLORS.place,
			name: 'a place',
			body: 'Where you were. `@helsinki`, `@the-office`. It tags the line the way a pattern does and points at nothing — only a `<pointer>` can put a line in a folder. An address is safe: `a@b.com` is just text, because a place has to start a word.'
		},
		{
			glyph: '--directive',
			color: SYNTAX_COLORS.directive,
			name: 'a directive',
			body: 'Files the line under that name as you send it, and is not part of the line afterwards. `--todo` makes a line tickable. Only ever in the capture bar.'
		}
	];
</script>

<svelte:head><title>Manual · Trophic</title></svelte:head>

<!-- The one capture screen that is a document rather than an instrument, so
     it says so: the shell clips what does not scroll itself. -->
<div class="flex min-h-0 flex-1 flex-col overflow-y-auto">
	<div class="flex shrink-0 items-center justify-between px-[34px] pt-[22px]">
		<a href="/settings" class="text-[13px] font-semibold text-neutral-700 hover:text-ink">
			← Settings
		</a>
	</div>

	<article class="mx-auto flex w-full max-w-[720px] flex-col gap-[34px] px-[34px] pt-[26px] pb-20">
		<header>
			<div class="text-[10px] font-bold tracking-[0.22em] text-accent-700 uppercase">Manual</div>
			<h1 class="mt-2 text-[52px] leading-[0.95] font-extrabold tracking-[-0.035em]">
				One line at a time
			</h1>
			<p class="mt-4 max-w-[560px] text-[17px] leading-[1.55] text-neutral-800">
				You type a line, attach what you made, press enter. The app files it and reads it back
				as a journal. Everything below is a consequence of that, and every rule exists because
				some other way of keeping a journal was found to lose things.
			</p>
		</header>

		<!-- 1 · The syntax -->
		<section class="flex flex-col gap-3">
			<h2 class="text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">
				1 · Four marks
			</h2>
			<p class="max-w-[600px] text-[15px] leading-[1.6] text-neutral-800">
				There are four, and none of them is required. A line with no marks on it is a
				perfectly good capture — it lands in the log, on today, unfiled, and stays there
				until you decide otherwise. The marks are how you say something extra without
				stopping to fill in a form.
			</p>
			<div class="mt-1 rounded-[16px] bg-surface px-[18px] py-2 shadow-md">
				{#each syntax as item (item.glyph)}
					<div class="flex flex-col gap-1.5 py-[15px]">
						<div class="flex items-baseline gap-3">
							<span class="font-mono text-[15px] font-medium" style="color:{item.color}">
								{item.glyph}
							</span>
							<span class="text-[13px] text-neutral-700">{item.name}</span>
						</div>
						<p class="text-[14px] leading-[1.55] text-neutral-800">{item.body}</p>
					</div>
				{/each}
			</div>
			<p class="max-w-[600px] text-[14px] leading-[1.6] text-neutral-700">
				<strong class="font-semibold text-ink">Tab completes a mark you have written before.</strong>
				The suggestions are ranked by what you actually use, and the list is drawn upwards from
				the caret, so the best match is nearest your thumb.
			</p>
		</section>

		<!-- 2 · Append-only -->
		<section class="flex flex-col gap-3">
			<h2 class="text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">
				2 · Nothing is ever edited
			</h2>
			<p class="max-w-[600px] text-[15px] leading-[1.6] text-neutral-800">
				The log is a file of lines that only ever grows. Every screen in this app is a
				<em>fold</em> over that file — the albums, the counts, the chapters, the sparklines,
				which folder an entry is in. None of it is stored anywhere; all of it is recomputed
				on the way to your eyes.
			</p>
			<div class="rounded-[16px] bg-surface px-[18px] py-4 shadow-md">
				<p class="text-[14px] leading-[1.6] text-neutral-800">
					Three things follow, and they are the reason for the whole arrangement:
				</p>
				<ul class="mt-3 flex flex-col gap-2.5 text-[14px] leading-[1.6] text-neutral-800">
					<li>
						<strong class="font-semibold">Ticking a box does not change a line.</strong> It appends
						the fact that you ticked it. Untick and that is appended too. The line you wrote at
						the time still says what it said.
					</li>
					<li>
						<strong class="font-semibold">The index is disposable.</strong> Delete it — there is a
						button in Settings — and the log rebuilds it exactly. If a number here cannot be
						recomputed from what you typed, it does not belong in the app.
					</li>
					<li>
						<strong class="font-semibold">Retuning the app re-scores all of history.</strong>
						Because nothing is baked in at write time, a change to how lines are read applies to
						every line you have ever written, with nothing to migrate.
					</li>
				</ul>
			</div>
		</section>

		<!-- 3 · Folders -->
		<section class="flex flex-col gap-3">
			<h2 class="text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">
				3 · A folder is a question, not a box
			</h2>
			<p class="max-w-[600px] text-[15px] leading-[1.6] text-neutral-800">
				An entry is in a folder because one of its tags points there — not because anything
				put it there. Point <span class="font-mono" style="color:{SYNTAX_COLORS.folder}"
					>&lt;deploy&gt;</span
				>
				at a folder in Settings and every entry you have <em>ever</em> written with that tag joins
				it, instantly, with nothing to backfill. Unpoint it and they leave again.
			</p>
			<p class="max-w-[600px] text-[15px] leading-[1.6] text-neutral-800">
				<strong class="font-semibold">The pin</strong> is the shortcut for a run of entries about
				one thing: pin a folder and every capture gets that folder's tag appended to the line
				itself. What is stored is a line that reads exactly as though you had typed the tag —
				which is why a pinned capture survives a rebuild like any other.
			</p>
			<p class="max-w-[600px] text-[15px] leading-[1.6] text-neutral-800">
				You can also file one line by hand: right-click it, or hold it on a touch screen.
			</p>
		</section>

		<!-- 4 · The Log -->
		<section class="flex flex-col gap-3">
			<h2 class="text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">
				4 · Reading it back
			</h2>
			<p class="max-w-[600px] text-[15px] leading-[1.6] text-neutral-800">
				<strong class="font-semibold">Albums restart each year.</strong> A folder belongs to a
				year, so a project running since 2024 is three albums rather than one endless scroll.
				That cap is what lets the month spine down the right edge stay twelve bars forever —
				an instrument you read at a glance instead of a list that grows.
			</p>
			<p class="max-w-[600px] text-[15px] leading-[1.6] text-neutral-800">
				<strong class="font-semibold">Chapters are month runs the app named from your own
					tags.</strong> Nothing invents a chapter title: it is the commonest pattern or tag inside
				that run of months, or the months themselves if there is nothing to use.
			</p>
			<p class="max-w-[600px] text-[15px] leading-[1.6] text-neutral-800">
				<strong class="font-semibold">Quiet stretches merge.</strong> Runs of days with a line or
				two and no media collapse into one strip. It is a merge and never a hide — the strip says
				how many lines it is holding, and expands into exactly the rows it replaced. Both this
				and the yearly restart are switches in Settings, and neither changes a stored byte.
			</p>
			<p class="max-w-[600px] text-[15px] leading-[1.6] text-neutral-800">
				Reaching history should never cost scrolling. The year rail, the month spine, the
				chapter list and the jump field are all one action, whatever the size of the journal.
				<strong class="font-semibold">Scrolling is for reading.</strong>
			</p>
		</section>

		<!-- 5 · Media and the connection -->
		<section class="flex flex-col gap-3">
			<h2 class="text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">
				5 · Photographs, clips, and a bad connection
			</h2>
			<p class="max-w-[600px] text-[15px] leading-[1.6] text-neutral-800">
				Files are uploaded when you press enter, not when you pick them — so changing your
				mind costs nothing and a five-minute video is never sent twice because you edited the
				line. The line goes in immediately and the files catch up behind it; the bar under the
				tabs is that happening.
			</p>
			<p class="max-w-[600px] text-[15px] leading-[1.6] text-neutral-800">
				Every original is kept byte for byte, and a smaller display copy is made beside it for
				the screen. Both are on this machine and nowhere else — which is what the
				<strong class="font-semibold">On disk</strong> panel in Settings is for, and why the
				backup button is beside it.
			</p>
			<p class="max-w-[600px] text-[15px] leading-[1.6] text-neutral-800">
				If the connection is dead when you press enter, the line is queued and sent when the
				browser comes back; the count of waiting lines is shown under the bar. If the
				<em>server</em> refuses, you get your text back instead. The two are different and the
				screen treats them differently, because losing a captured thought is the one thing
				this app must never do.
			</p>
		</section>

		<!-- 6 · Absent -->
		<section class="flex flex-col gap-3">
			<h2 class="text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">
				6 · What is deliberately missing
			</h2>
			<div class="rounded-[16px] bg-surface px-[18px] py-4 shadow-md">
				<p class="text-[14px] leading-[1.6] text-neutral-800">
					No notifications. No streaks, scores or nudges. No editing or deleting a line — a
					wrong entry is corrected by writing the correction. No sharing, no accounts, no
					second user. No links: paste one and the bar refuses it, because this is a place for
					your own words.
				</p>
				<p class="mt-3 text-[14px] leading-[1.6] text-neutral-800">
					Patterns are counted and drawn and <strong class="font-semibold">never
						interpreted</strong>. These are refusals rather than gaps.
				</p>
			</div>
		</section>
	</article>
</div>
