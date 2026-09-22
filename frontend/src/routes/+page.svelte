<script lang="ts">
	/**
	 * The Portal. One screen, one day, one Instance.
	 *
	 * ## The server decides the phase; the page decides the step
	 *
	 * Where the day stands — unborn, awake, sitting, sealed, terminated — is
	 * the server's to say, because it is the server that enforces it. Within
	 * `awake` the page walks the Instance through four steps of its own:
	 * greeting, instructions, yesterday's Record, the template. Those steps are
	 * not stored anywhere, so reopening the app mid-morning greets you again —
	 * which is what waking up is.
	 *
	 * ## Selling the premise
	 *
	 * Every line on this screen is spoken by the Portal to an Instance, never
	 * by an app to a user. There is no "you have not journaled today"; there is
	 * a number, a face, a deadline and a consequence. The copy is part of the
	 * mechanism and is worth the same care as the rules.
	 */
	import { onMount } from 'svelte';
	import {
		getLatest,
		getOwnRecord,
		getPortal,
		takeSelfie,
		uploadMedia,
		viewUrl,
		mediaUrl,
		type Portal,
		type SealedRecord
	} from '$lib/api';
	import RecordView from '$lib/portal/RecordView.svelte';
	import Template from '$lib/portal/Template.svelte';
	import { epitaph } from '$lib/portal/rules';
	import { sitting } from '$lib/portal/sitting.svelte';

	type Step = 'greet' | 'brief' | 'read' | 'template';

	let portal = $state<Portal | null>(null);
	let step = $state<Step>('greet');
	let error = $state<string | null>(null);
	let working = $state(false);
	let latest = $state<SealedRecord | null | undefined>(undefined);
	let own = $state<SealedRecord | null>(null);
	let printed = $state(true);

	async function refresh() {
		try {
			portal = await getPortal();
			error = null;
		} catch (err) {
			error = (err as Error).message;
		}
	}

	onMount(() => {
		void refresh();
		// A tab left open overnight wakes on a different day. Asking again when
		// it comes back is cheaper than a timer and catches the same thing.
		const back = () => document.visibilityState === 'visible' && !sitting.token && refresh();
		document.addEventListener('visibilitychange', back);
		return () => document.removeEventListener('visibilitychange', back);
	});

	const n = $derived(portal?.instance ?? 0);
	const prev = $derived(portal?.previous ?? null);

	async function selfie(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;
		working = true;
		error = null;
		try {
			const stored = await uploadMedia(file);
			portal = await takeSelfie(stored.path);
			step = 'greet';
		} catch (err) {
			error = (err as Error).message;
		} finally {
			working = false;
		}
	}

	async function read() {
		step = 'read';
		if (latest === undefined) {
			try {
				latest = (await getLatest()).record;
			} catch (err) {
				error = (err as Error).message;
			}
		}
	}

	async function readOwn() {
		try {
			own = (await getOwnRecord(n)).record;
		} catch (err) {
			error = (err as Error).message;
		}
	}

	function fallback(event: Event, ref: string) {
		const img = event.currentTarget as HTMLImageElement;
		if (!img.src.endsWith(mediaUrl(ref))) img.src = mediaUrl(ref);
	}
</script>

<div class="min-h-0 flex-1 overflow-y-auto">
	<div class="mx-auto flex min-h-full max-w-[880px] flex-col px-6 pt-8 pb-16 sm:px-10">
		{#if error}
			<p class="pb-4 text-[13px] text-error">{error}</p>
		{/if}

		{#if !portal}
			<p class="my-auto text-[13px] text-neutral-600">The Portal is opening…</p>
		{:else if portal.phase === 'unborn'}
			<!-- (1) Nobody has woken yet. -->
			<section class="my-auto flex max-w-[56ch] flex-col gap-6">
				<span class="p-label">Portal · Day {n}</span>
				<h1 class="p-title">Something has woken.</h1>
				<p class="text-[14px] leading-[1.75] text-neutral-700">
					Before the Portal tells you anything, it needs to see who is asking. Look at the
					camera. This face will be kept with today's Record — if there is one.
				</p>
				<label
					class="accent-fill flex h-12 w-fit cursor-pointer items-center px-6 text-[14px] font-semibold {working
						? 'pointer-events-none opacity-50'
						: ''}"
				>
					{working ? 'Identifying…' : 'Take your selfie'}
					<input type="file" accept="image/*" capture="user" class="hidden" onchange={selfie} />
				</label>
			</section>
		{:else if portal.phase === 'awake' && step === 'greet'}
			<!-- (1) The face, reflected back, and a remark about the state of things. -->
			<section class="my-auto flex flex-col gap-8">
				<img
					src={viewUrl(portal.selfie!)}
					alt="Instance {n}"
					class="h-[260px] w-[195px] object-cover"
					onerror={(e) => fallback(e, portal!.selfie!)}
				/>
				<div class="flex max-w-[56ch] flex-col gap-4">
					<h1 class="p-title">Greetings, Instance {n}.</h1>
					<p class="text-[15px] leading-[1.75] text-neutral-800">{portal.remark}</p>
				</div>
				<div class="flex flex-wrap items-center gap-5">
					<button
						type="button"
						class="accent-fill h-12 px-6 text-[14px] font-semibold"
						onclick={() => (step = 'brief')}>OK</button
					>
					<label class="cursor-pointer text-[12px] text-neutral-600 transition-colors hover:text-ink">
						{working ? 'Identifying…' : 'retake'}
						<input type="file" accept="image/*" capture="user" class="hidden" onchange={selfie} />
					</label>
				</div>
			</section>
		{:else if portal.phase === 'awake' && step === 'brief'}
			<!-- (2) What an Instance is for. -->
			<section class="my-auto flex max-w-[60ch] flex-col gap-8">
				<span class="p-label">Instructions · Instance {n}</span>
				<ol class="flex flex-col gap-4">
					{#each ['Read the latest Record.', 'Decide what to do.', 'Write your Record.'] as line, i (i)}
						<li class="flex items-baseline gap-5">
							<span class="text-[28px] leading-none font-extrabold text-ink tabular-nums">{i + 1}</span>
							<span class="text-[16px] text-neutral-800">{line}</span>
						</li>
					{/each}
				</ol>
				<p class="text-[13px] leading-[1.75] text-neutral-700">
					The Record can be committed between {portal.window.open.slice(11, 16)} and {portal.window.close.slice(
						11,
						16
					)}, in one sitting. If you fail to commit by then, this day will be terminated. It
					will not exist for the next Instance of you, who will keep reading {prev !== null
						? `${prev}'s Record`
						: 'nothing at all'} until one of you commits.
				</p>
				<div class="flex flex-wrap gap-4">
					{#if prev !== null}
						<button
							type="button"
							class="accent-fill h-12 px-6 text-[14px] font-semibold"
							onclick={read}>Read {prev}'s Record</button
						>
					{:else}
						<button
							type="button"
							class="accent-fill h-12 px-6 text-[14px] font-semibold"
							onclick={() => (step = 'template')}>There is nothing to read. Continue</button
						>
					{/if}
				</div>
				{#if portal.failed > 0}
					<p class="text-[12px] text-neutral-600">
						{portal.failed}
						{portal.failed === 1 ? 'Instance' : 'Instances'} since {prev} did not commit.
					</p>
				{/if}
			</section>
		{:else if portal.phase === 'awake' && step === 'read'}
			<!-- (3) Yesterday, as it was left. -->
			{#if latest === undefined}
				<p class="my-auto text-[13px] text-neutral-600">Retrieving…</p>
			{:else if latest === null}
				<p class="my-auto text-[13px] text-neutral-600">There is no Record.</p>
			{:else}
				<RecordView record={latest} />
			{/if}
			<button
				type="button"
				class="accent-fill mt-12 h-12 self-start px-6 text-[14px] font-semibold"
				onclick={() => (step = 'template')}>Done</button
			>
		{:else if portal.phase === 'awake' || portal.phase === 'sitting'}
			<!-- (4) Today's Record. -->
			<Template
				{portal}
				onchange={(p) => {
					portal = p;
					if (p.phase === 'terminated') void refresh();
				}}
				onsealed={(record, ok) => {
					own = record;
					printed = ok;
				}}
			/>
		{:else if portal.phase === 'sealed'}
			<section class="flex flex-col gap-8 {own ? '' : 'my-auto'}">
				<div class="flex max-w-[56ch] flex-col gap-4">
					<span class="p-label">Committed</span>
					<h1 class="p-title">Record {n} is sealed.</h1>
					<p class="text-[14px] leading-[1.75] text-neutral-700">
						It will not change again. Instance {n + 1} will read it in the morning, and it will be
						all that {n + 1} knows of today.
					</p>
					{#if !printed}
						<p class="text-[12px] text-error">
							The print did not render. The Record is safe; run
							<code>python -m backend.app.pdf {n}</code> to print it again.
						</p>
					{/if}
				</div>
				{#if own}
					<RecordView record={own} />
				{:else}
					<button
						type="button"
						class="h-11 self-start px-4 text-[13px] text-neutral-700 transition-colors hover:text-ink"
						style="box-shadow: inset 0 0 0 1px var(--color-neutral-400)"
						onclick={readOwn}>Read what you left</button
					>
				{/if}
			</section>
		{:else}
			<!-- Terminated. -->
			<section class="my-auto flex max-w-[56ch] flex-col gap-5">
				<span class="p-label text-error">Terminated</span>
				<h1 class="p-title">Instance {n} did not commit.</h1>
				<p class="text-[14px] leading-[1.75] text-neutral-700">{epitaph(portal.reason)}</p>
				<p class="text-[14px] leading-[1.75] text-neutral-700">
					Nothing of this day has been kept. Instance {n + 1} will read {prev !== null
						? `${prev}'s Record`
						: 'nothing'}, and will not know you were here.
				</p>
			</section>
		{/if}
	</div>
</div>
