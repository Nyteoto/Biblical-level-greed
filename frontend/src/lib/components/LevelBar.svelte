<script lang="ts">
	import type { Xp } from '$lib/api';

	interface Props {
		xp: Xp;
	}

	let { xp }: Props = $props();

	let open = $state(false);

	const b = $derived(xp.today_breakdown);
	const pct = (n: number) => `${Math.round(n)}%`;
</script>

<section class="mb-7">
	<div class="mb-1.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
		<span class="font-mono text-[13px] tracking-[0.14em] text-stone-200 uppercase">
			Level {xp.level}
		</span>

		{#if xp.streak > 1}
			<span class="font-mono text-[11px] text-amber-400">
				{xp.streak}-day streak
				<span class="text-stone-600">·{Math.round((b.streak_mult - 1) * 100)}%</span>
			</span>
		{/if}

		{#if b.spread_penalised}
			<!-- The only place the app ever tells you off. It is the arithmetic
			     from the seasons work, restated as a number. -->
			<span
				class="font-mono text-[11px] text-rose-400"
				title="{b.acquiring_domains.join(', ')} are all in season today"
			>
				spread over {b.acquiring_domains.length} domains
				<span class="text-stone-600">−{Math.round((1 - b.spread_mult) * 100)}%</span>
			</span>
		{/if}

		<button
			onclick={() => (open = !open)}
			class="ml-auto font-mono text-[11px] tabular-nums text-stone-500 hover:text-stone-300"
			aria-expanded={open}
		>
			{#if xp.earned_today > 0}
				<span class="text-amber-300">+{Math.round(xp.earned_today)}</span>
			{/if}
			<span class="text-stone-600">
				{Math.round(xp.into_level)}/{Math.round(xp.level_span)}
			</span>
			<span class="text-stone-700">{open ? '▾' : '▸'}</span>
		</button>
	</div>

	<div class="flex h-2 w-full overflow-hidden rounded-full bg-black/50">
		<!-- White: carried in from yesterday. Yellow: earned today. Two sections
		     rather than one so the day's work is visible as its own quantity. -->
		<div
			class="h-full bg-stone-200/90 transition-all duration-500"
			style="width: {xp.carried_pct}%"
		></div>
		<div class="h-full bg-amber-400 transition-all duration-500" style="width: {xp.today_pct}%"></div>
	</div>

	{#if open}
		<dl class="mt-2 space-y-0.5 border-l border-stone-800 pl-3 font-mono text-[11px]">
			<div class="flex justify-between">
				<dt class="text-stone-600">{b.sessions} sessions, tier-weighted</dt>
				<dd class="text-stone-400">{Math.round(b.session_xp)}</dd>
			</div>
			<div class="flex justify-between">
				<dt class="text-stone-600">× streak ({xp.streak} days)</dt>
				<dd class="text-stone-400">{b.streak_mult.toFixed(2)}</dd>
			</div>
			<div class="flex justify-between">
				<dt class="text-stone-600">
					× spread ({b.acquiring_domains.length} in season)
				</dt>
				<dd class={b.spread_penalised ? 'text-rose-400' : 'text-stone-400'}>
					{b.spread_mult.toFixed(2)}
				</dd>
			</div>
			{#if b.todos}
				<div class="flex justify-between">
					<dt class="text-stone-600">+ {b.todos} checklist (flat, no bonuses)</dt>
					<dd class="text-stone-400">{Math.round(b.todo_xp)}</dd>
				</div>
			{/if}
			<div class="flex justify-between border-t border-stone-800 pt-0.5">
				<dt class="text-stone-500">today</dt>
				<dd class="text-amber-300">{Math.round(xp.earned_today)}</dd>
			</div>
			<p class="pt-1 text-[10px] text-stone-700">
				Derived from the log, stored nowhere, and it never changes what the board shows
				you. Rates live in <span class="text-stone-600">backend/app/xp.py</span>; retuning
				them re-scores everything at once.
			</p>
		</dl>
	{/if}
</section>
