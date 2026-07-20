<script lang="ts">
	// Throwaway diagnostic. Deletes cleanly once we know the answer.
	//
	// Question: does `shortcuts://` fire from an INSTALLED PWA in standalone
	// mode? Apple documents the scheme for browsers and says nothing about
	// standalone, so it gets settled by experiment rather than by reading.
	//
	// Self-verifying: the test Shortcut POSTs back to /api/shortcut-ping, so a
	// hit is server-side proof it ran. The page cannot fool itself.

	const SHORTCUT = 'PGS Test';
	const enc = encodeURIComponent(SHORTCUT);

	let origin = $state('');
	let standalone = $state<boolean | null>(null);
	let ping = $state<{ at: string | null; count: number; note: string } | null>(null);
	let polling = $state(false);

	$effect(() => {
		origin = location.origin;
		// iOS sets navigator.standalone; the media query is the cross-platform way.
		standalone =
			// @ts-expect-error — iOS-only, not in the DOM types
			navigator.standalone === true ||
			window.matchMedia('(display-mode: standalone)').matches;
		poll();
	});

	async function poll() {
		polling = true;
		try {
			ping = await (await fetch('/api/shortcut-ping')).json();
		} catch {
			ping = null;
		}
		polling = false;
	}

	// Re-check whenever the tab is shown again — which is exactly what happens
	// when iOS bounces you back from the Shortcuts app.
	$effect(() => {
		const onShow = () => document.visibilityState === 'visible' && poll();
		document.addEventListener('visibilitychange', onShow);
		return () => document.removeEventListener('visibilitychange', onShow);
	});

	const tests = $derived([
		{
			n: 1,
			label: 'Open the Shortcuts app',
			href: 'shortcuts://',
			why: 'Does iOS honour the scheme at all from here? If this fails, nothing else can work.'
		},
		{
			n: 2,
			label: `Run "${SHORTCUT}"`,
			href: `shortcuts://run-shortcut?name=${enc}`,
			why: 'The plain form. Runs it, but leaves you in the Shortcuts app.'
		},
		{
			n: 3,
			label: `Run "${SHORTCUT}" and come back`,
			href: `shortcuts://x-callback-url/run-shortcut?name=${enc}&x-success=${encodeURIComponent(
				origin + '/shortcut-test'
			)}`,
			why: 'x-callback-url. If this returns you here automatically, the round trip works and the photo flow is viable.'
		}
	]);
</script>

<svelte:head><title>Shortcut test</title></svelte:head>

<div class="mx-auto max-w-2xl px-6 py-8 text-[13px] leading-relaxed text-stone-400">
	<h1 class="text-[15px] font-semibold tracking-[0.24em] text-stone-200 uppercase">
		Shortcut test
	</h1>

	<div class="mt-3 rounded-sm border border-stone-800 bg-black/20 px-4 py-3 font-mono text-[11px]">
		<div>
			display mode:
			<span class={standalone ? 'text-emerald-400' : 'text-amber-400'}>
				{standalone === null ? '…' : standalone ? 'standalone (installed PWA) ✓' : 'browser tab'}
			</span>
		</div>
		<div class="text-stone-600">
			{standalone === false ? 'Open this from the home-screen icon — a Safari tab is the easy case.' : ''}
		</div>
	</div>

	<!-- Step 0 -->
	<section class="mt-6">
		<h2 class="mb-1 text-[11px] font-semibold tracking-[0.2em] text-amber-300/90 uppercase">
			First, make the Shortcut
		</h2>
		<p>
			On the iPad: Shortcuts app → <span class="text-stone-300">+</span> → add the action
			<span class="font-mono text-stone-300">Get Contents of URL</span>, set it to
		</p>
		<pre class="my-2 overflow-x-auto rounded-sm border border-stone-800 bg-black/30 px-3 py-2 font-mono text-[11px] text-stone-300">POST  {origin}/api/shortcut-ping
Request Body: JSON
   text = it ran</pre>
		<p>
			Name it exactly <span class="font-mono text-stone-200">{SHORTCUT}</span>. It needs to do
			nothing else — the POST is how we prove it ran.
		</p>
	</section>

	<!-- Tests -->
	<section class="mt-6">
		<h2 class="mb-2 text-[11px] font-semibold tracking-[0.2em] text-amber-300/90 uppercase">
			Then tap these in order
		</h2>
		<div class="space-y-2">
			{#each tests as t (t.n)}
				<div class="rounded-sm border border-stone-800 bg-black/20 px-4 py-3">
					<a
						href={t.href}
						class="text-[14px] font-medium text-amber-300 underline underline-offset-4"
					>
						{t.n}. {t.label}
					</a>
					<p class="mt-1 text-[12px] text-stone-500">{t.why}</p>
				</div>
			{/each}
		</div>
	</section>

	<!-- Result -->
	<section class="mt-6">
		<h2 class="mb-2 text-[11px] font-semibold tracking-[0.2em] text-amber-300/90 uppercase">
			Did the Shortcut reach the server?
		</h2>
		<div
			class="rounded-sm border px-4 py-3 font-mono text-[12px]
			{ping?.count ? 'border-emerald-500/50 bg-emerald-500/5' : 'border-stone-800 bg-black/20'}"
		>
			{#if ping?.count}
				<div class="text-emerald-300">YES — {ping.count} hit(s)</div>
				<div class="mt-1 text-stone-500">last: {ping.at}</div>
				{#if ping.note}<div class="text-stone-500">body: {ping.note}</div>{/if}
			{:else}
				<div class="text-stone-500">no hits yet</div>
			{/if}
		</div>
		<button
			onclick={poll}
			disabled={polling}
			class="mt-2 rounded-sm border border-stone-700 px-3 py-1.5 text-[11px] tracking-[0.16em] text-stone-300 uppercase hover:border-stone-600 disabled:opacity-30"
		>
			{polling ? 'checking…' : 'check again'}
		</button>
		<p class="mt-2 text-[11px] text-stone-600">
			This also re-checks automatically whenever the page becomes visible again, which is what
			happens when iOS bounces you back.
		</p>
	</section>

	<p class="mt-8 border-t border-stone-800 pt-4 text-[11px] text-stone-600">
		Tell me which of the three worked and whether 3 returned you here by itself. Then this page
		gets deleted.
	</p>
</div>
