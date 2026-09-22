<script lang="ts">
	/**
	 * A sealed Record, as the next Instance reads it: the record sheet with ink
	 * in its boxes and the stamp on it. Nothing here is editable and nothing
	 * offers to be.
	 *
	 * The register is numbered by paragraph, the way the reference numbers its
	 * lines, and the ruled lines the Instance did not use are left blank, as a
	 * form leaves them. Video plays on its plate — the one thing the print
	 * cannot do, where a clip is its poster frame and its filename.
	 */
	import { mediaUrl, pdfUrl, viewUrl, type SealedRecord } from '$lib/api';
	import MoodScale from './MoodScale.svelte';
	import Plate from './Plate.svelte';
	import Sheet, { type Fact } from './Sheet.svelte';
	import { until } from './rules';

	let { record }: { record: SealedRecord } = $props();

	/** The register's rows: one per paragraph, blank lines kept out. */
	const rows = $derived(
		record.body
			.split(/\n+/)
			.map((line) => line.trim())
			.filter(Boolean)
	);
	/** Enough unused lines under the writing that the register reads as a form. */
	const blanks = $derived(Math.max(3, 9 - rows.length));

	const time = (iso: string) => iso.slice(11, 16);
	const facts = $derived<Fact[]>([
		// No "sealed" here: the stamp on the register already says when.
		{ label: 'began', value: time(record.sitting.began) },
		{
			label: 'took',
			value: until(Date.parse(record.sitting.sealed) - Date.parse(record.sitting.began))
		}
	]);

	function fallback(event: Event, ref: string) {
		const img = event.currentTarget as HTMLImageElement;
		if (!img.src.endsWith(mediaUrl(ref))) img.src = mediaUrl(ref);
	}
</script>

<Sheet
	instance={record.instance}
	day={record.day}
	selfie={record.selfie}
	{facts}
	filed={record.follows !== null}
	previous={record.follows}
	stamp={{ label: 'sealed', time: time(record.sitting.sealed) }}
	plateCount={String(record.media.length)}
>
	{#snippet register()}
		{#each rows as row, i (i)}
			<div class="flex" style="box-shadow: inset 0 -1px 0 0 var(--color-neutral-400)">
				<span class="w-[42px] shrink-0 pt-3 text-center text-[11px] text-neutral-600 tabular-nums"
					>{String(i + 1).padStart(2, '0')}</span
				>
				<p
					class="m-0 min-w-0 flex-1 px-3.5 pt-[9px] pb-[11px] text-[16px] leading-[1.5] font-light whitespace-pre-wrap text-neutral-800"
					style="box-shadow: inset 1px 0 0 0 var(--color-neutral-400)"
				>
					{row}
				</p>
			</div>
		{/each}
		{#each { length: blanks } as _, i (i)}
			<div aria-hidden="true" class="flex h-[34px]" style="box-shadow: inset 0 -1px 0 0 var(--color-rule-faint)">
				<span class="w-[42px] pt-[11px] text-center text-[11px] tabular-nums" style="color:#2a3138"
					>{String(rows.length + i + 1).padStart(2, '0')}</span
				>
				<span class="flex-1" style="box-shadow: inset 1px 0 0 0 var(--color-rule-faint)"></span>
			</div>
		{/each}
	{/snippet}

	{#snippet plates()}
		{#if record.media.length}
			<div class="grid grid-cols-2 gap-3">
				{#each record.media as item, i (item.ref)}
					{@const large = i === 0 || item.kind === 'video'}
					<div class={large ? 'col-span-2' : ''}>
						<Plate {large}>
							{#if item.kind === 'video'}
								<!-- svelte-ignore a11y_media_has_caption -->
								<video
									src={mediaUrl(item.ref)}
									poster={viewUrl(item.ref)}
									controls
									playsinline
									preload="metadata"
									class="h-full w-full bg-neutral-300 object-contain"
								></video>
							{:else}
								<a
									href={mediaUrl(item.ref)}
									target="_blank"
									rel="noopener"
									aria-label="plate {i + 1}, open full size"
									class="block h-full w-full"
								>
									<img
										src={viewUrl(item.ref)}
										alt={item.caption}
										class="h-full w-full bg-neutral-300 object-cover"
										onerror={(e) => fallback(e, item.ref)}
									/>
								</a>
							{/if}
							{#snippet caption()}
								<span class="shrink-0 font-bold text-neutral-800">pl. {i + 1}</span>
								{#if item.kind === 'video'}<span class="shrink-0">clip</span>{/if}
								<span class="min-w-0 truncate normal-case tracking-normal text-neutral-700"
									>{item.caption}</span
								>
							{/snippet}
						</Plate>
					</div>
				{/each}
			</div>
		{:else}
			<p class="text-[12px] text-neutral-600">No plates were mounted.</p>
		{/if}
	{/snippet}

	{#snippet forward()}
		<p class="m-0 mt-1.5 text-[14px] leading-[1.6] font-light whitespace-pre-wrap text-neutral-800">
			{record.wish}
		</p>
	{/snippet}

	{#snippet mood()}
		<MoodScale value={record.mood} />
	{/snippet}

	{#snippet signed()}
		<span class="text-[22px] font-extrabold tracking-[-0.02em] text-ink">{record.signature}</span>
	{/snippet}
</Sheet>

{#if record.pdf}
	<a
		href={pdfUrl(record.instance)}
		target="_blank"
		rel="noopener"
		class="mt-4 inline-block text-[11px] tracking-[0.16em] text-neutral-600 uppercase transition-colors hover:text-ink"
		>{record.instance}.pdf ↗</a
	>
{/if}
