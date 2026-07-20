<script lang="ts">
	import type { Todo } from '$lib/api';

	interface Props {
		items: Todo[];
		today: string;
		busy?: boolean;
		onadd: (text: string) => Promise<unknown> | unknown;
		oncomplete: (id: string) => Promise<unknown> | unknown;
	}

	let { items, today, busy = false, onadd, oncomplete }: Props = $props();

	let draft = $state('');

	// Ticked items vanish on the next load. Fading them immediately makes the
	// click feel answered without pretending the write already succeeded.
	let leaving = $state<string[]>([]);

	function submit(event: SubmitEvent) {
		event.preventDefault();
		const text = draft.trim();
		if (!text || busy) return;
		draft = '';
		onadd(text);
	}

	function tick(id: string) {
		if (leaving.includes(id)) return;
		leaving = [...leaving, id];
		oncomplete(id);
	}

	const DAY = 86_400_000;

	/** The list never resets, so an item can sit here for weeks. Say so quietly
	 * — an errand you have carried for nine days is information. */
	function age(added: string): string {
		const days = Math.round(
			(new Date(today + 'T00:00:00').getTime() - new Date(added + 'T00:00:00').getTime()) / DAY
		);
		return days >= 1 ? `${days}d` : '';
	}
</script>

<section class="mb-7">
	<h3 class="mb-2 text-[10px] font-semibold tracking-[0.2em] text-stone-700 uppercase">
		Checklist
	</h3>

	<div class="rounded-sm border border-stone-800/60 bg-black/20">
		{#if items.length}
			<ul>
				{#each items as item (item.id)}
					{@const going = leaving.includes(item.id)}
					{@const old = age(item.added)}
					<li class="border-b border-stone-800/40 last:border-b-0">
						<button
							onclick={() => tick(item.id)}
							disabled={going}
							class="group flex w-full items-center gap-3 px-3 py-2 text-left transition hover:bg-black/30
							{going ? 'opacity-30' : ''}"
						>
							<span
								class="flex h-4 w-4 shrink-0 items-center justify-center rounded-[2px] border transition
								{going
									? 'border-emerald-500/60 bg-emerald-500/20'
									: 'border-stone-700 group-hover:border-emerald-500/60'}"
								aria-hidden="true"
							>
								{#if going}
									<svg viewBox="0 0 12 12" class="h-2.5 w-2.5 text-emerald-300" fill="none">
										<path
											d="M2 6.5L4.5 9L10 3"
											stroke="currentColor"
											stroke-width="2"
											stroke-linecap="round"
											stroke-linejoin="round"
										/>
									</svg>
								{/if}
							</span>
							<span class="flex-1 text-[13px] text-stone-300 {going ? 'line-through' : ''}">
								{item.text}
							</span>
							{#if old}
								<span class="shrink-0 font-mono text-[10px] text-stone-700">{old}</span>
							{/if}
						</button>
					</li>
				{/each}
			</ul>
		{/if}

		<form onsubmit={submit} class="flex items-center gap-2 px-3 py-2">
			<span class="h-4 w-4 shrink-0 rounded-[2px] border border-dashed border-stone-800"></span>
			<input
				bind:value={draft}
				type="text"
				placeholder={items.length ? 'Something else' : 'Buy strings, email the studio…'}
				aria-label="Add a checklist item"
				class="flex-1 bg-transparent text-[13px] text-stone-200 placeholder:text-stone-700 focus:outline-none"
			/>
			{#if draft.trim()}
				<button
					type="submit"
					disabled={busy}
					class="shrink-0 rounded-sm border border-stone-700 px-2 py-0.5 text-[10px] tracking-[0.16em] text-stone-400 uppercase hover:border-stone-600 disabled:opacity-30"
				>
					add
				</button>
			{/if}
		</form>
	</div>
</section>
