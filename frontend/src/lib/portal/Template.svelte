<script lang="ts">
	/**
	 * Today's Record, being written — or waiting to be.
	 *
	 * ## One template, two states
	 *
	 * Outside a sitting every field is drawn and none can be touched: the
	 * Instance sees exactly what it will have to fill before it commits to
	 * filling it, which is the fairest thing a one-sitting rule can do. Inside
	 * one, the same fields come alive and a checklist beside the commit button
	 * says what still stands between the draft and a Record.
	 *
	 * ## What is fixed and what is written
	 *
	 * The date, the instance number and the selfie are the Portal's, not the
	 * Instance's — they are stated rather than asked for. The signature starts
	 * as the instance number and may be anything; it is a field because signing
	 * is an act, even when what is signed is a number.
	 *
	 * ## Media arrive before the Record does
	 *
	 * A photo or a clip is uploaded and attached the moment it is chosen,
	 * because a clip can be gigabytes and a commit that waited on it could miss
	 * the window. So the media are the one part of the draft the server holds —
	 * attached to the sitting, deleted with it if it ends. The text never is.
	 */
	import {
		ApiError,
		attachMedia,
		beginSitting,
		commit,
		detachMedia,
		mediaUrl,
		posterFor,
		sendPoster,
		uploadMedia,
		viewUrl,
		type Portal,
		type SealedRecord
	} from '$lib/api';
	import MoodScale from './MoodScale.svelte';
	import Plate from './Plate.svelte';
	import Sheet, { type Fact } from './Sheet.svelte';
	import { draft, end, hold, sitting } from './sitting.svelte';
	import { missing, until } from './rules';

	let {
		portal,
		onchange,
		onsealed
	}: {
		portal: Portal;
		onchange: (p: Portal) => void;
		onsealed: (record: SealedRecord, printed: boolean) => void;
	} = $props();

	const n = $derived(portal.instance);
	const live = $derived(portal.phase === 'sitting' && sitting.token !== null);
	/** A sitting the server knows about and this page does not hold: another
	 *  screen, or this one before a reload. */
	const elsewhere = $derived(portal.phase === 'sitting' && sitting.token === null);

	// The server's clock, not the device's: a phone set five minutes fast must
	// not be told the window is open when the server will refuse it.
	const skew = $derived(Date.parse(portal.now) - Date.now());
	let tick = $state(Date.now());
	$effect(() => {
		const id = setInterval(() => (tick = Date.now()), 1000);
		return () => clearInterval(id);
	});
	const now = $derived(tick + skew);
	const opens = $derived(Date.parse(portal.window.open));
	const closes = $derived(Date.parse(portal.window.close));
	const isOpen = $derived(now >= opens && now < closes);

	const pictures = $derived(
		(portal.selfie ? 1 : 0) + portal.media.filter((m) => m.kind === 'image').length
	);
	const gaps = $derived(missing(draft, pictures));

	/** The tally row: facts about this sheet, never totals across sheets. The
	 *  time left is not here — the bar above says it, and stays on screen
	 *  while the sheet scrolls. */
	const facts = $derived<Fact[]>([
		{
			label: 'window',
			value: `${portal.window.open.slice(11, 16)}–${portal.window.close.slice(11, 16)}`
		},
		{ label: 'began', value: portal.began ? portal.began.slice(11, 16) : '—', dim: !portal.began },
		{ label: 'lost since', value: String(portal.failed), dim: portal.failed === 0 }
	]);

	let error = $state<string | null>(null);
	let busy = $state(false);
	/** The two-press seal: the first press arms, the second commits. */
	let arming = $state(false);
	let upload = $state<{ name: string; fraction: number } | null>(null);

	async function begin() {
		busy = true;
		error = null;
		try {
			const opened = await beginSitting();
			hold(opened.token, String(opened.instance));
			onchange(opened);
		} catch (err) {
			error = (err as Error).message;
		} finally {
			busy = false;
		}
	}

	/** A 410 or a 403 means the sitting is over; hand the page back to the
	 *  parent, which will find the day terminated. */
	function refused(err: unknown) {
		if (err instanceof ApiError && (err.status === 410 || err.status === 403)) {
			end(err.message);
			onchange({ ...portal, phase: 'terminated' });
			return;
		}
		error = (err as Error).message;
	}

	async function add(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file || !sitting.token) return;
		error = null;
		upload = { name: file.name, fraction: 0 };
		try {
			const video = file.type.startsWith('video/');
			const poster = video ? posterFor(file) : Promise.resolve(null);
			const stored = await uploadMedia(file, (f) => upload && (upload.fraction = f));
			const next = await attachMedia(sitting.token!, stored.path);
			onchange(next);
			// After attaching, not before: the server only takes a poster for a
			// clip the day already holds.
			const frame = await poster;
			if (frame) await sendPoster(stored.path, frame);
		} catch (err) {
			refused(err);
		} finally {
			upload = null;
		}
	}

	async function remove(ref: string) {
		if (!sitting.token) return;
		try {
			onchange(await detachMedia(sitting.token, ref));
			delete draft.captions[ref];
		} catch (err) {
			refused(err);
		}
	}

	async function seal() {
		if (!sitting.token || gaps.length) return;
		if (!arming) {
			arming = true;
			return;
		}
		busy = true;
		error = null;
		try {
			const sealed = await commit(sitting.token, $state.snapshot(draft));
			end();
			onchange(sealed);
			onsealed(sealed.record, sealed.printed);
		} catch (err) {
			arming = false;
			refused(err);
		} finally {
			busy = false;
		}
	}

	function fallback(event: Event, ref: string) {
		const img = event.currentTarget as HTMLImageElement;
		if (!img.src.endsWith(mediaUrl(ref))) img.src = mediaUrl(ref);
	}

	/** `19:00`, read straight off the server's ISO stamp — which carries the
	 *  Portal's zone — so the page never has to know what that zone is. */
	const clock = (iso: string) => iso.slice(11, 16);
</script>

<div class="flex flex-col gap-10">
	<!-- The state of the sitting, above the page it governs. -->
	<div
		class="sticky top-0 z-10 -mx-6 flex flex-wrap items-center gap-x-6 gap-y-3 bg-ground px-6 py-4 sm:-mx-10 sm:px-10"
		style="box-shadow: inset 0 -1px 0 0 var(--color-neutral-400)"
	>
		{#if live}
			<span class="p-label text-ink">Sitting</span>
			<span class="text-[13px] text-neutral-700 tabular-nums">
				{until(closes - now)} until the window closes
			</span>
		{:else if elsewhere}
			<span class="text-[13px] text-neutral-700">
				A sitting is under way on another screen. If that screen is gone, the day ends
				within {Math.round(portal.grace / 60)} minutes of its last word.
			</span>
		{:else if !isOpen && now < opens}
			<span class="p-label">Locked</span>
			<span class="text-[13px] text-neutral-700 tabular-nums">
				The window opens at {clock(portal.window.open)} — in {until(opens - now)}.
			</span>
		{:else if isOpen}
			<div class="flex max-w-[60ch] flex-col gap-1.5">
				<span class="text-[13px] text-neutral-800">
					The window is open until {clock(portal.window.close)}.
				</span>
				<span class="text-[12px] leading-[1.6] text-neutral-600">
					A Record is written in one sitting. Once it begins, leaving this page — closing
					it, reloading it, or going silent for {Math.round(portal.grace / 60)} minutes — ends
					the day, and nothing of it is kept.
				</span>
			</div>
			<button
				type="button"
				class="accent-fill ml-auto h-11 px-5 text-[13px] font-semibold disabled:opacity-50"
				disabled={busy}
				onclick={begin}>Begin sitting</button
			>
		{:else}
			<span class="text-[13px] text-neutral-700">The window has closed.</span>
		{/if}
	</div>

	{#if error}
		<p class="-mt-6 text-[13px] text-error">{error}</p>
	{/if}

	<!-- The sheet. Disabled as a whole outside a sitting, so the Instance sees
	     every box it will have to fill before it commits to filling them. -->
	<fieldset disabled={!live} class="m-0 min-w-0 border-0 p-0 {live ? '' : 'opacity-60'}">
		<Sheet
			instance={n}
			day={portal.day}
			selfie={portal.selfie}
			{facts}
			filed={portal.previous !== null}
			previous={portal.previous !== null && portal.previous_day
				? { instance: portal.previous, day: portal.previous_day }
				: null}
			plateCount="{portal.media.length} of {portal.max_media}"
		>
			{#snippet register()}
				<!-- Written straight onto the ruled lines. The rules are the
				     textarea's own background, attached to its content, so they
				     scroll with the writing rather than sitting still under it. -->
				<textarea
					aria-label="The day"
					class="ruled field-sizing-content min-h-[408px] w-full flex-1 resize-none bg-transparent pr-3.5 pl-[56px] text-[16px] leading-[34px] font-light text-neutral-800 placeholder:text-neutral-600"
					placeholder="What happened. What you did. What you would want to know tomorrow."
					bind:value={draft.body}
				></textarea>
			{/snippet}

			{#snippet plates()}
				<div class="grid grid-cols-2 gap-3">
					{#each portal.media as item, i (item.ref)}
						{@const large = i === 0 || item.kind === 'video'}
						<div class="relative {large ? 'col-span-2' : ''}">
							<Plate {large}>
								{#if item.kind === 'video'}
									<!-- svelte-ignore a11y_media_has_caption -->
									<video
										src={mediaUrl(item.ref)}
										controls
										playsinline
										preload="metadata"
										class="h-full w-full bg-neutral-300 object-contain"
									></video>
								{:else}
									<img
										src={viewUrl(item.ref)}
										alt=""
										class="h-full w-full bg-neutral-300 object-cover"
										onerror={(e) => fallback(e, item.ref)}
									/>
								{/if}
								{#snippet caption()}
									<span class="shrink-0 font-bold text-neutral-800">pl. {i + 1}</span>
									<input
										type="text"
										aria-label="A note under plate {i + 1}"
										placeholder="a note, if you want one"
										class="h-7 min-w-0 flex-1 bg-transparent text-[12px] tracking-normal text-neutral-800 normal-case placeholder:text-neutral-600"
										style="box-shadow: inset 0 -1px 0 0 var(--color-neutral-400)"
										bind:value={draft.captions[item.ref]}
									/>
									<button
										type="button"
										class="h-7 shrink-0 text-neutral-600 hover:text-ink"
										onclick={() => remove(item.ref)}>remove</button
									>
								{/snippet}
							</Plate>
						</div>
					{/each}

					{#if upload}
						<div class={portal.media.length === 0 ? 'col-span-2' : ''}>
							<Plate large={portal.media.length === 0}>
								<div class="flex h-full flex-col items-center justify-center gap-3 bg-neutral-200">
									<span class="max-w-[80%] truncate text-[11px] text-neutral-700">{upload.name}</span>
									<span class="h-[3px] w-1/2 bg-neutral-400">
										<span
											class="block h-full bg-ink"
											style="width: {Math.round(upload.fraction * 100)}%"
										></span>
									</span>
								</div>
							</Plate>
						</div>
					{:else if portal.media.length < portal.max_media}
						<!-- An empty mount, waiting for a plate. -->
						<div class={portal.media.length === 0 ? 'col-span-2' : ''}>
							<Plate large={portal.media.length === 0}>
								<label
									class="flex h-full cursor-pointer flex-col items-center justify-center gap-1 text-neutral-600 transition-colors hover:text-ink"
								>
									<span class="text-[20px] leading-none">+</span>
									<span class="text-[10px] tracking-[0.14em] uppercase">mount a plate</span>
									<input type="file" accept="image/*,video/*" class="hidden" onchange={add} />
								</label>
							</Plate>
						</div>
					{/if}
				</div>
			{/snippet}

			{#snippet forward()}
				<textarea
					aria-label="What do you want {n + 1} to do?"
					class="field-sizing-content mt-1.5 min-h-[96px] w-full resize-none bg-transparent text-[14px] leading-[1.6] font-light text-neutral-800"
					bind:value={draft.wish}
				></textarea>
			{/snippet}

			{#snippet mood()}
				<MoodScale value={draft.mood} onpick={live ? (m) => (draft.mood = m) : undefined} />
			{/snippet}

			{#snippet signed()}
				<input
					type="text"
					aria-label="Signed"
					class="h-10 w-full bg-transparent text-[22px] font-extrabold tracking-[-0.02em] text-ink"
					style="box-shadow: inset 0 -1px 0 0 var(--color-neutral-500)"
					placeholder={String(n)}
					bind:value={draft.signature}
				/>
			{/snippet}
		</Sheet>
	</fieldset>

	{#if live}
		<section class="flex flex-col gap-4 pb-6">
			{#if gaps.length}
				<div class="flex flex-col gap-1.5">
					<span class="p-label">Still missing</span>
					{#each gaps as gap (gap)}
						<span class="text-[13px] text-neutral-700">— {gap}</span>
					{/each}
				</div>
			{/if}
			<div class="flex flex-wrap items-center gap-4">
				<button
					type="button"
					class="h-12 px-6 text-[14px] font-semibold transition-colors disabled:opacity-40 {gaps.length
						? 'text-neutral-600'
						: 'accent-fill'}"
					style={gaps.length ? 'box-shadow: inset 0 0 0 1px var(--color-neutral-400)' : ''}
					disabled={busy || gaps.length > 0}
					onclick={seal}
				>
					{#if busy}
						Sealing…
					{:else if arming}
						Seal Record {n}. It can never be changed.
					{:else}
						Commit
					{/if}
				</button>
				{#if arming && !busy}
					<button
						type="button"
						class="h-12 px-3 text-[13px] text-neutral-600 hover:text-ink"
						onclick={() => (arming = false)}>not yet</button
					>
				{/if}
			</div>
		</section>
	{/if}
</div>
