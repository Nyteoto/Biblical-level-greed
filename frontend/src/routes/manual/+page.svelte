<script lang="ts">
	// The manual is deliberately static: no fetch, no state, nothing that can be
	// out of date with the server. Everything here is a claim about design, and
	// the numbers in it are the ones the trees were actually built from.
	const kinds = [
		['drill', 'distinct days', 'Repetition. Decays without upkeep — hands rot, so `decay_days` sends them back to maintenance.'],
		['study', 'distinct days', 'Comprehension. Holds once held, so nothing here ever goes stale.'],
		['project', 'phases, not days', 'One indivisible burst. A film shoot is four fourteen-hour days after three idle weeks — you cannot do 12% of a shoot day, so a counter would lie.'],
		['exam', 'prep days + a date', 'Scored by someone else, on their calendar. If nobody else is scoring you, it is not an exam.'],
		['social', 'occasions', 'Needs other people. Never forced to complete, because you cannot schedule someone else.']
	];

	const shapes = [
		['ladder', 'exactly one', 'Levels that genuinely nest, like HSK.'],
		['strands', 'one per strand', 'Tracks a real curriculum runs at once. Berklee teaches harmony, ear training and technique in the same semester on purpose — showing one would starve the others.'],
		['cycles', 'project + what feeds it', 'AFI has you direct three complete films before you are ready for any of them. The craft serves the film in front of you.']
	];

	const seasons = [
		['high', 'the full board, or only the strands the season names', 'The one or two domains you are actually acquiring.'],
		['low', 'only nodes about to go stale', 'Holding ground. On a quiet week this shows nothing, which is the correct answer.'],
		['off', 'nothing at all', 'Only legal where nothing decays. The loader refuses it otherwise.']
	];
</script>

<svelte:head><title>Manual · Personal Growth System</title></svelte:head>

<article class="mx-auto max-w-3xl px-6 py-10 text-[13px] leading-relaxed text-stone-400">
	<header class="mb-10">
		<h1 class="text-[15px] font-semibold tracking-[0.24em] text-stone-200 uppercase">Manual</h1>
		<p class="mt-2 text-stone-500">
			How to use this, and why it is built the way it is. Every rule below exists because
			a specific way of tracking practice was found to lie.
		</p>
	</header>

	<!-- 1 -->
	<section class="mb-9">
		<h2 class="mb-2 text-[11px] font-semibold tracking-[0.2em] text-amber-300/90 uppercase">
			1 · The one question
		</h2>
		<p>
			<strong class="text-stone-200">What do I work on right now, and for how long?</strong>
			Everything on the <span class="text-stone-300">Today</span> screen answers that and
			nothing else. Open it, do what the cards say, click them off, close it. If you are
			ever deciding <em>what</em> to do rather than doing it, the board has failed.
		</p>
	</section>

	<!-- 2 -->
	<section class="mb-9">
		<h2 class="mb-2 text-[11px] font-semibold tracking-[0.2em] text-amber-300/90 uppercase">
			2 · Reading Today
		</h2>
		<dl class="space-y-2 border-l border-stone-800 pl-4">
			<div>
				<dt class="text-stone-300">Declared today</dt>
				<dd>
					The sum of every active card's minimum, added up from what you typed. Not advice
					— arithmetic. It exists because the cost of a board was the one input that was
					never visible, and six domains at once came to <span class="font-mono text-stone-300">10.2 h/day</span>
					without ever saying so.
				</dd>
			</div>
			<div>
				<dt class="text-stone-300">Level bar</dt>
				<dd>
					White is what yesterday left you with; amber is what today added. Levelling up
					collapses the white to zero, because none of the new level was there yesterday.
				</dd>
			</div>
			<div>
				<dt class="text-stone-300">Checklist</dt>
				<dd>
					Errands, not practice. No tier, no gate, no accrual. Ticking removes the item;
					the list never resets, and shows an item's age once it is over a day old.
				</dd>
			</div>
			<div>
				<dt class="text-stone-300">Out of season</dt>
				<dd>
					Domains you are holding rather than advancing. Empty is the normal state and
					means nothing is owed — it is not the same as having finished.
				</dd>
			</div>
		</dl>
	</section>

	<!-- 3 -->
	<section class="mb-9">
		<h2 class="mb-2 text-[11px] font-semibold tracking-[0.2em] text-amber-300/90 uppercase">
			3 · Gate, entry, estimate
		</h2>
		<p class="mb-3">
			Three fields on every node, answering three different questions. They are the whole
			model.
		</p>
		<div class="space-y-2 border-l border-stone-800 pl-4">
			<p>
				<strong class="text-stone-200">Gate</strong> — what "done" actually means, in a
				sentence. <em>The app never reads it.</em> You decide when it is true and press
				complete. Accrual is the machine's job; judgement is yours.
			</p>
			<p>
				<strong class="text-stone-200">Entry</strong> — where to <em>start</em>: the book,
				the free course, the search string that returns the right thing. It exists because a
				tree of titles and gates is only usable by someone who already knows the field.
				It shows on a card until the first session, then gets out of the way.
			</p>
			<p>
				<strong class="text-stone-200">Estimate</strong> — a <em>guess</em> at how many days
				this takes. Not a target, not a contract. You may finish under it, and you may keep
				logging past it; both are measurements of the guess, and the node reports the gap.
				Sessions logged after completion are upkeep, not cost, and are excluded.
			</p>
		</div>
		<p class="mt-3 text-stone-500">
			The estimates shipped here are known to be low — the nine Teach Yourself CS subjects
			get 66 h each against its own 100–200. They were left low deliberately: the point is
			to find the real multiplier from completed nodes rather than invent a second set of
			numbers to be wrong about.
		</p>
	</section>

	<!-- 4 -->
	<section class="mb-9">
		<h2 class="mb-2 text-[11px] font-semibold tracking-[0.2em] text-amber-300/90 uppercase">
			4 · Node kinds
		</h2>
		<p class="mb-3">A node's kind decides how it accrues and whether it can complete.</p>
		<div class="overflow-x-auto">
			<table class="w-full border-collapse text-left">
				<thead>
					<tr class="border-b border-stone-800 text-[10px] tracking-[0.14em] text-stone-600 uppercase">
						<th class="py-1.5 pr-3 font-normal">kind</th>
						<th class="py-1.5 pr-3 font-normal">accrues</th>
						<th class="py-1.5 font-normal">why it exists</th>
					</tr>
				</thead>
				<tbody>
					{#each kinds as [kind, accrues, why]}
						<tr class="border-b border-stone-800/50 align-top">
							<td class="py-1.5 pr-3 font-mono text-amber-300/80">{kind}</td>
							<td class="py-1.5 pr-3 whitespace-nowrap text-stone-500">{accrues}</td>
							<td class="py-1.5">{why}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	</section>

	<!-- 5 -->
	<section class="mb-9">
		<h2 class="mb-2 text-[11px] font-semibold tracking-[0.2em] text-amber-300/90 uppercase">
			5 · Shapes, and hard vs soft
		</h2>
		<div class="mb-4 overflow-x-auto">
			<table class="w-full border-collapse text-left">
				<thead>
					<tr class="border-b border-stone-800 text-[10px] tracking-[0.14em] text-stone-600 uppercase">
						<th class="py-1.5 pr-3 font-normal">shape</th>
						<th class="py-1.5 pr-3 font-normal">active at once</th>
						<th class="py-1.5 font-normal">taken from</th>
					</tr>
				</thead>
				<tbody>
					{#each shapes as [shape, active, why]}
						<tr class="border-b border-stone-800/50 align-top">
							<td class="py-1.5 pr-3 font-mono text-amber-300/80">{shape}</td>
							<td class="py-1.5 pr-3 whitespace-nowrap text-stone-500">{active}</td>
							<td class="py-1.5">{why}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<p>
			A solid edge is <strong class="text-stone-200">hard</strong>: the node is locked until
			its prerequisite is complete. A dashed edge is <strong class="text-stone-200">soft</strong>:
			advice, ordered after, startable now anyway.
		</p>
		<p class="mt-2 text-stone-500">
			This distinction is the sharpest claim in the system. Every edge in
			<span class="font-mono">electrical-engineering</span> is hard, because attempting
			signals and systems without linear algebra produces zero progress. Almost every edge in
			<span class="font-mono">filmmaking</span> is soft, because being unready is the method —
			a locked first film would teach the opposite. The same tree structure means opposite
			things, so the file has to say which.
		</p>
	</section>

	<!-- 6 -->
	<section class="mb-9">
		<h2 class="mb-2 text-[11px] font-semibold tracking-[0.2em] text-amber-300/90 uppercase">
			6 · Seasons — deliberate neglect
		</h2>
		<p class="mb-3">
			Six domains acquiring at once is <span class="font-mono text-stone-300">~10 h/day</span>.
			Six domains merely <em>held</em> is <span class="font-mono text-stone-300">~33 min/day</span>.
			You can hold six things; you cannot learn six things at once. Seasons are the mechanism
			for that difference, and they are the most important control here.
		</p>
		<div class="mb-3 overflow-x-auto">
			<table class="w-full border-collapse text-left">
				<thead>
					<tr class="border-b border-stone-800 text-[10px] tracking-[0.14em] text-stone-600 uppercase">
						<th class="py-1.5 pr-3 font-normal">state</th>
						<th class="py-1.5 pr-3 font-normal">shows</th>
						<th class="py-1.5 font-normal">for</th>
					</tr>
				</thead>
				<tbody>
					{#each seasons as [state, shows, why]}
						<tr class="border-b border-stone-800/50 align-top">
							<td class="py-1.5 pr-3 font-mono text-amber-300/80">{state}</td>
							<td class="py-1.5 pr-3">{shows}</td>
							<td class="py-1.5 text-stone-500">{why}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
		<p>
			Low season needs no configuration, because <span class="font-mono">decay_days</span>
			already said what a held domain owes you: a node reappears once it is within a quarter
			of its own window. A 14-day drill returns at 11 idle days; a 180-day one at 135.
		</p>
		<p class="mt-2">
			A season ends on <strong class="text-stone-200">a date or a shipped node, whichever
			lands first</strong>. A trigger alone deadlocks when the project stalls — which is what
			projects do — and a date alone throws away the reward for finishing early. The app
			tells you the season is over and offers the switch; it never flips it for you.
		</p>
		<p class="mt-2 text-stone-500">
			Set it per domain under <span class="text-stone-400">Tech Tree → edit</span>.
		</p>
	</section>

	<!-- 7 -->
	<section class="mb-9">
		<h2 class="mb-2 text-[11px] font-semibold tracking-[0.2em] text-amber-300/90 uppercase">
			7 · What the app refuses to do
		</h2>
		<ul class="space-y-1.5 border-l border-stone-800 pl-4">
			<li>
				<strong class="text-stone-200">It never decides for you.</strong> No timers, no
				minute tracking, no notifications. A click carries no duration, so no minute is
				recorded that was not measured.
			</li>
			<li>
				<strong class="text-stone-200">It never scores the decision.</strong> XP exists, and
				it is fenced off — a read-only projection that cannot reach which node is active,
				what is due, or what a season does. There is a test asserting the board does not
				import it.
			</li>
			<li>
				<strong class="text-stone-200">It never rewrites history.</strong> The log is
				append-only. Undo appends; completion appends; a ticked checklist item appends. The
				list forgets, the file does not.
			</li>
			<li>
				<strong class="text-stone-200">It never interprets a number.</strong> Metric
				readings are stored and drawn. Nothing changes because of one.
			</li>
		</ul>
		<p class="mt-3 text-stone-500">
			The point of all four: the board must be predictable by reading the
			<span class="font-mono">.toml</span>. If you cannot predict it at a glance, that is a
			bug — not a feature you have not learned yet.
		</p>
	</section>

	<!-- 8 -->
	<section class="mb-9">
		<h2 class="mb-2 text-[11px] font-semibold tracking-[0.2em] text-amber-300/90 uppercase">
			8 · Your data
		</h2>
		<p>
			Plain files, in <span class="font-mono text-stone-300">data/</span>. Trees are hand-editable
			TOML; the log and checklist are append-only JSONL; the SQLite index is a disposable
			cache you can delete at any time. Editing a tree in the UI rewrites the whole file, so
			comments in it do not survive — the rationale lives in
			<span class="font-mono">docs/sources.md</span> instead.
		</p>
		<p class="mt-2">
			Running on two machines: point both at one shared folder and there is nothing to sync,
			or use a private git remote, where the append-only log merges without conflicts. See
			<span class="font-mono text-stone-300">SYNC.md</span>.
		</p>
	</section>

	<footer class="border-t border-stone-800 pt-4 text-stone-600">
		<p>
			The trees shipped here are sequenced from HSK 3.0, the Berklee guitar and drum cores,
			MIT 6-5, Teach Yourself CS and the AFI directing curriculum. What was researched and
			what was chosen are separated honestly in
			<span class="font-mono">docs/sources.md</span>.
		</p>
	</footer>
</article>
