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
	import { draft, end, hold, sitting } from './sitting.svelte';
	import { longDay, missing, until } from './rules';

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

	<fieldset disabled={!live} class="flex flex-col gap-10 {live ? '' : 'opacity-60'}">
		<header class="flex flex-wrap items-start justify-between gap-6">
			<div class="flex flex-col gap-3">
				<span class="p-label">{longDay(portal.day)}</span>
				<h1 class="p-title">Instance {n}</h1>
			</div>
			{#if portal.selfie}
				<img
					src={viewUrl(portal.selfie)}
					alt="Instance {n}"
					class="h-[168px] w-[126px] object-cover"
					onerror={(e) => fallback(e, portal.selfie!)}
				/>
			{/if}
		</header>

		<section class="flex flex-col gap-3">
			<h2 class="p-label">Media · {portal.media.length} of {portal.max_media}</h2>
			<div class="grid grid-cols-1 gap-6 sm:grid-cols-2">
				{#each portal.media as item (item.ref)}
					<figure class="flex flex-col gap-2">
						<div class="relative">
							{#if item.kind === 'video'}
								<!-- svelte-ignore a11y_media_has_caption -->
								<video
									src={mediaUrl(item.ref)}
									controls
									playsinline
									preload="metadata"
									class="aspect-video w-full bg-neutral-200 object-contain"
								></video>
							{:else}
								<img
									src={viewUrl(item.ref)}
									alt=""
									class="max-h-[360px] w-full bg-neutral-200 object-contain"
									onerror={(e) => fallback(e, item.ref)}
								/>
							{/if}
							<button
								type="button"
								class="absolute top-2 right-2 h-9 bg-ground px-3 text-[12px] text-neutral-700 hover:text-ink"
								onclick={() => remove(item.ref)}>remove</button
							>
						</div>
						<input
							type="text"
							placeholder="A note under it, if you want one"
							class="h-10 bg-transparent px-0 text-[13px] text-neutral-800 placeholder:text-neutral-600"
							style="box-shadow: inset 0 -1px 0 0 var(--color-neutral-400)"
							bind:value={draft.captions[item.ref]}
						/>
					</figure>
				{/each}

				{#if upload}
					<div class="flex aspect-video flex-col items-center justify-center gap-3 bg-neutral-200">
						<span class="max-w-[80%] truncate text-[12px] text-neutral-700">{upload.name}</span>
						<span class="h-[3px] w-1/2 bg-neutral-400">
							<span
								class="block h-full bg-ink"
								style="width: {Math.round(upload.fraction * 100)}%"
							></span>
						</span>
					</div>
				{:else if portal.media.length < portal.max_media}
					<label
						class="flex aspect-video cursor-pointer flex-col items-center justify-center gap-1 text-neutral-600 transition-colors hover:text-ink"
						style="box-shadow: inset 0 0 0 1px var(--color-neutral-400)"
					>
						<span class="text-[22px] leading-none">+</span>
						<span class="text-[12px]">a photo or a clip</span>
						<input type="file" accept="image/*,video/*" class="hidden" onchange={add} />
					</label>
				{/if}
			</div>
		</section>

		<section class="flex max-w-[68ch] flex-col gap-3">
			<h2 class="p-label">Record</h2>
			<textarea
				class="field-sizing-content min-h-[220px] resize-none bg-neutral-200 p-4 text-[14px] leading-[1.75] text-neutral-800"
				placeholder="What happened. What you did. What you would want to know tomorrow."
				bind:value={draft.body}
			></textarea>
		</section>

		<section class="flex max-w-[68ch] flex-col gap-3">
			<h2 class="p-label">What do you want {n + 1} to do?</h2>
			<textarea
				class="field-sizing-content min-h-[110px] resize-none bg-neutral-200 p-4 text-[14px] leading-[1.75] text-neutral-800"
				bind:value={draft.wish}
			></textarea>
		</section>

		<section class="flex flex-col gap-3">
			<h2 class="p-label">On a scale of 1 to 10, how do you feel?</h2>
			<MoodScale value={draft.mood} onpick={live ? (m) => (draft.mood = m) : undefined} />
		</section>

		<section class="flex max-w-[360px] flex-col gap-2">
			<h2 class="p-label">Signed</h2>
			<input
				type="text"
				class="h-12 bg-transparent text-[22px] font-extrabold tracking-[-0.02em] text-ink"
				style="box-shadow: inset 0 -1px 0 0 var(--color-neutral-400)"
				placeholder={String(n)}
				bind:value={draft.signature}
			/>
		</section>
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
