<script lang="ts">
	// Where anything that is neither the board nor a note goes: what the app is
	// costing on disk today, and whatever gets measured or configured next.
	// Deliberately one page with sections rather than a nest of tabs — there is
	// not enough here yet to justify navigation.
	import { bytes, getStorage, type StorageReport } from '$lib/api';

	let report = $state<StorageReport | null>(null);
	let error = $state<string | null>(null);
	let loading = $state(true);

	async function load() {
		loading = true;
		try {
			report = await getStorage();
			error = null;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		load();
	});

	// Widths are relative to the biggest slice, not the total: with one part at
	// 90% every other bar would be invisible, which is when you most want to see
	// what the small ones are.
	const largest = $derived(Math.max(1, ...(report?.parts ?? []).map((p) => p.bytes)));
</script>

<div class="mx-auto w-full max-w-3xl px-6 py-8">
	<h1 class="text-[13px] tracking-[0.22em] text-stone-400 uppercase">Settings</h1>

	<!-- Storage ------------------------------------------------------------ -->
	<section class="mt-7">
		<div class="flex items-baseline justify-between gap-3">
			<h2 class="text-[11px] tracking-[0.18em] text-amber-300/90 uppercase">Storage</h2>
			<button
				onclick={load}
				disabled={loading}
				class="text-[10px] tracking-[0.16em] text-stone-600 uppercase hover:text-stone-400 disabled:text-stone-700"
			>
				{loading ? 'reading…' : 'refresh'}
			</button>
		</div>

		{#if error}
			<p class="mt-3 rounded-sm border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-[12px] text-rose-200">
				{error}
			</p>
		{:else if report}
			<div class="mt-3 rounded-sm border border-stone-800/80 bg-black/20">
				<div class="flex items-baseline justify-between border-b border-stone-800/80 px-4 py-3">
					<div>
						<div class="text-2xl text-stone-100">{bytes(report.total_bytes)}</div>
						<div class="mt-0.5 font-mono text-[10px] text-stone-600">
							{report.total_files} files · {report.path}
						</div>
					</div>
				</div>

				<div class="divide-y divide-stone-800/60">
					{#each report.parts as part (part.key)}
						<div class="px-4 py-3">
							<div class="flex items-baseline justify-between gap-3">
								<span class="text-[13px] text-stone-200">
									{part.label}
									{#if part.recoverable}
										<span
											class="ml-1.5 rounded-sm border border-stone-800 px-1.5 py-px font-mono text-[9px] tracking-wider text-stone-500 uppercase"
											title="Derived data — deleting it only costs a rebuild"
										>
											rebuildable
										</span>
									{/if}
								</span>
								<span class="shrink-0 font-mono text-[12px] text-stone-400">
									{bytes(part.bytes)}
								</span>
							</div>

							<div class="mt-1.5 h-1 overflow-hidden rounded-full bg-stone-900">
								<div
									class="h-full rounded-full {part.recoverable
										? 'bg-stone-600'
										: 'bg-amber-500/70'}"
									style="width: {part.bytes === 0
										? 0
										: Math.max(1.5, (part.bytes / largest) * 100)}%"
								></div>
							</div>

							<p class="mt-1.5 text-[11px] leading-relaxed text-stone-600">
								{part.files}
								{part.files === 1 ? 'file' : 'files'} · {part.hint}
							</p>
						</div>
					{/each}
				</div>
			</div>
		{:else}
			<p class="mt-3 text-[12px] text-stone-600">reading…</p>
		{/if}
	</section>

	<!-- Reference ----------------------------------------------------------- -->
	<section class="mt-8">
		<h2 class="text-[11px] tracking-[0.18em] text-amber-300/90 uppercase">Reference</h2>
		<a
			href="/manual"
			class="mt-3 flex items-center gap-3 rounded-sm border border-stone-800/80 bg-black/20 px-4 py-3 transition hover:border-stone-700"
		>
			<div class="min-w-0 flex-1">
				<div class="text-[13px] text-stone-200">Manual</div>
				<p class="mt-0.5 text-[11px] leading-relaxed text-stone-600">
					What the node kinds, domain shapes and seasons mean, and why the model is shaped
					this way.
				</p>
			</div>
			<span class="shrink-0 text-stone-600">→</span>
		</a>
	</section>
</div>
