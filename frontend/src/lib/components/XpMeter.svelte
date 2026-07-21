<script lang="ts">
	import type { Xp } from '$lib/api';

	interface Props {
		xp: Xp;
	}

	let { xp }: Props = $props();

	let open = $state(false);
	const b = $derived(xp.today_breakdown);

	// The bank leads. The level is a record of what you have done and cannot be
	// spent; the bank is the number you make decisions with, so it is the one
	// that gets read at a glance.
	const bank = $derived(Math.floor(xp.bank));
</script>

<div class="relative flex items-center gap-3">
	<button
		onclick={() => (open = !open)}
		class="flex items-center gap-2.5 rounded-sm px-2 py-1 transition hover:bg-white/5"
		title="Bank: {bank} XP to spend · Level {xp.level}"
	>
		<span class="font-mono text-[13px] tabular-nums text-amber-300">{bank}</span>
		<span class="text-[9px] tracking-[0.16em] text-amber-500/70 uppercase">xp</span>

		<span class="flex flex-col items-start gap-0.5">
			<span class="font-mono text-[9px] tracking-wider text-stone-500">
				lv {xp.level}
				{#if xp.streak > 1}
					<span class="text-stone-600">· {xp.streak}d</span>
				{/if}
			</span>
			<!-- Two sections, as before: what carried in, then what today added. -->
			<span class="flex h-[3px] w-24 overflow-hidden rounded-full bg-black/60">
				<span class="h-full bg-amber-200/40" style="width: {xp.carried_pct}%"></span>
				<span
					class="h-full bg-amber-400 transition-all duration-500"
					style="width: {xp.today_pct}%"
				></span>
			</span>
		</span>

		{#if xp.earned_today > 0}
			<span class="font-mono text-[10px] text-amber-300/80">+{Math.round(xp.earned_today)}</span>
		{/if}
	</button>

	{#if open}
		<!-- The arithmetic, on demand. The number has to stay predictable now that
		     it decides what you can start. -->
		<div
			class="absolute top-full right-0 z-50 mt-1 w-72 rounded-sm border border-stone-800 bg-[#171310] p-3 shadow-xl"
		>
			<dl class="space-y-1 text-[11px]">
				<div class="flex justify-between">
					<dt class="text-stone-500">earned, lifetime</dt>
					<dd class="font-mono text-stone-300">{Math.round(xp.total)}</dd>
				</div>
				<div class="flex justify-between">
					<dt class="text-stone-500">spent on unlocks</dt>
					<dd class="font-mono text-stone-400">−{Math.round(xp.spent)}</dd>
				</div>
				<div class="flex justify-between border-t border-stone-800 pt-1">
					<dt class="text-stone-400">bank</dt>
					<dd class="font-mono text-amber-300">{bank}</dd>
				</div>
			</dl>

			<div class="mt-2.5 border-t border-stone-800 pt-2">
				<p class="text-[10px] tracking-[0.14em] text-stone-600 uppercase">today</p>
				<dl class="mt-1 space-y-1 text-[11px]">
					<div class="flex justify-between">
						<dt class="text-stone-500">
							{b.sessions} sessions
							{#if b.upkeep_sessions}
								<span class="text-stone-600">({b.upkeep_sessions} upkeep)</span>
							{/if}
						</dt>
						<dd class="font-mono text-stone-400">{Math.round(b.session_xp)}</dd>
					</div>
					{#if b.todos}
						<div class="flex justify-between">
							<dt class="text-stone-500">{b.todos} todos</dt>
							<dd class="font-mono text-stone-400">{Math.round(b.todo_xp)}</dd>
						</div>
					{/if}
					<div class="flex justify-between">
						<dt class="text-stone-500">× streak ({xp.streak} days)</dt>
						<dd class="font-mono text-stone-400">{b.streak_mult}</dd>
					</div>
					<div class="flex justify-between">
						<dt class={b.focused ? 'text-amber-300/80' : 'text-stone-500'}>
							× focus ({b.acquiring_domains.length} acquiring)
						</dt>
						<dd class="font-mono {b.focused ? 'text-amber-300/80' : 'text-stone-400'}">
							{b.focus_mult}
						</dd>
					</div>
					{#if !b.focused}
						<p class="pt-0.5 text-[10px] leading-relaxed text-stone-600">
							Acquiring in {b.acquiring_domains.length} domains. Drop to
							{xp.tunables.focus_domains} to earn the full focus bonus.
						</p>
					{/if}
				</dl>
			</div>

			<p class="mt-2.5 border-t border-stone-800 pt-2 text-[10px] leading-relaxed text-stone-600">
				Levels record what you did and never fall. The bank is what starting
				something costs — and no single node can earn its way to the next tier.
			</p>
		</div>
	{/if}
</div>
