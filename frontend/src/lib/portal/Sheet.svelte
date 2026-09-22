<script lang="ts">
	/**
	 * The record sheet: one day, drawn as a form filed in a binder.
	 *
	 * ## Why a form
	 *
	 * The reference is the design canvas's *One day, as a record sheet*, and it
	 * fits the Portal better than the day it was drawn for. A Record is exactly
	 * a form — fixed fields, filled once, filed, never amended — and the
	 * premise needs it to *look* filed: the sheets underneath are the Records
	 * before this one, the binder holes say it belongs to a set, and the stamp
	 * says when it was sealed. A page of prose could be edited tomorrow; a
	 * stamped form evidently was not.
	 *
	 * ## One sheet, written and read
	 *
	 * The template and the read-back Record are the same component, so the
	 * next Instance reads the form in the shape it was filled in. What differs
	 * is only what goes in the boxes — inputs or ink — and that arrives as
	 * snippets. The frame, the header, the rules and the stamp are drawn here
	 * once. The print (`pdf.py`) draws the same form on paper.
	 *
	 * ## What is not on it
	 *
	 * No counts that could be read as a score. The tally row holds facts about
	 * *this* sheet — which Record it follows, how many Instances failed in
	 * between, when the sitting began — and never a total across sheets.
	 */
	import type { Snippet } from 'svelte';
	import { mediaUrl, viewUrl } from '$lib/api';

	export interface Fact {
		label: string;
		value: string;
		/** Drawn at the ramp's quiet rung, for a fact that is an absence. */
		dim?: boolean;
	}

	let {
		instance,
		day,
		selfie,
		facts,
		filed = true,
		stamp = null,
		previous = null,
		plates,
		plateCount,
		register,
		forward,
		mood,
		signed
	}: {
		instance: number;
		day: string;
		selfie: string | null;
		facts: Fact[];
		/** Whether earlier sheets lie underneath — false for the very first. */
		filed?: boolean;
		stamp?: { label: string; time: string } | null;
		/** The sheet this one follows, for the foot. */
		previous?: { instance: number; day: string } | null;
		plates: Snippet;
		plateCount: string;
		register: Snippet;
		forward: Snippet;
		mood: Snippet;
		signed: Snippet;
	} = $props();

	const MONTHS = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC'];
	const DAYS = ['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'];

	function parts(d: string) {
		const [y, m, dd] = d.split('-').map(Number);
		const weekday = DAYS[new Date(Date.UTC(y, m - 1, dd)).getUTCDay()];
		return { date: `${String(dd).padStart(2, '0')} ${MONTHS[m - 1]} ${String(y).slice(2)}`, weekday };
	}

	const when = $derived(parts(day));
	const prev = $derived(previous ? parts(previous.day) : null);

	function fallback(event: Event, ref: string) {
		const img = event.currentTarget as HTMLImageElement;
		if (!img.src.endsWith(mediaUrl(ref))) img.src = mediaUrl(ref);
	}
</script>

<div class="relative md:pr-[21px] md:pb-[21px]">
	{#if filed}
		<!-- The sheets filed underneath: the Records before this one. -->
		<div
			aria-hidden="true"
			class="absolute top-[21px] right-0 bottom-0 left-[21px] hidden md:block"
			style="background:#0f1317;box-shadow:inset 0 0 0 1px #1c2228"
		></div>
		<div
			aria-hidden="true"
			class="absolute top-[14px] right-[7px] bottom-[7px] left-[14px] hidden md:block"
			style="background:#11161a;box-shadow:inset 0 0 0 1px #222830"
		></div>
		<div
			aria-hidden="true"
			class="absolute top-[7px] right-[14px] bottom-[14px] left-[7px] hidden md:block"
			style="background:#13181d;box-shadow:inset 0 0 0 1px #2a3138"
		></div>
	{/if}

	<article
		class="relative bg-sheet px-4 pt-5 pb-4 md:pr-7 md:pl-20"
		style="box-shadow: inset 0 0 0 1px var(--color-neutral-500)"
	>
		<!-- Punched for the binder, with the margin rule beside the holes. -->
		{#each ['118px', '380px', '642px'] as top (top)}
			<span
				aria-hidden="true"
				class="absolute left-[22px] hidden h-4 w-4 rounded-full bg-ground md:block"
				style="top:{top};box-shadow:inset 0 1px 2px rgba(0,0,0,0.6),0 0 0 1px var(--color-neutral-400)"
			></span>
		{/each}
		<span
			aria-hidden="true"
			class="absolute top-0 bottom-0 left-[60px] hidden w-px bg-neutral-400 md:block"
		></span>

		<!-- The form's title line. -->
		<div class="flex items-baseline gap-3.5 pb-2.5">
			<span class="text-[13px] font-extrabold tracking-[0.3em] text-neutral-800 uppercase"
				>Record</span
			>
			<!-- The reference ends this line with the sheet's number. Here that
			     number is already the header's own box, and a sheet says a
			     thing once. -->
			<span class="h-px flex-1 self-center bg-neutral-400"></span>
		</div>

		<!-- The header: a ruled grid of labelled boxes, and the subject's face. -->
		<div class="f-grid grid-cols-[minmax(0,1fr)_auto]">
			<div class="grid min-w-0 gap-px">
				<div class="grid grid-cols-2 gap-px sm:grid-cols-[minmax(0,1.6fr)_88px_minmax(0,1fr)]">
					<div class="f-cell col-span-2 sm:col-span-1">
						<div class="f-label">date</div>
						<div
							class="mt-1.5 text-[30px] leading-none font-extrabold tracking-[-0.035em] text-ink tabular-nums sm:text-[38px]"
						>
							{when.date}
						</div>
					</div>
					<div class="f-cell">
						<div class="f-label">day</div>
						<div class="mt-3.5 text-[20px] font-bold text-neutral-800">{when.weekday}</div>
					</div>
					<div class="f-cell">
						<div class="f-label">instance</div>
						<div class="mt-3.5 text-[20px] font-bold text-neutral-800 tabular-nums">{instance}</div>
					</div>
				</div>
				<div
					class="grid gap-px"
					style="grid-template-columns: repeat(auto-fit, minmax(118px, 1fr))"
				>
					{#each facts as fact (fact.label)}
						<div class="f-cell flex items-center justify-between gap-2 pt-[7px] pb-[9px]">
							<span class="f-label">{fact.label}</span>
							<span
								class="text-[15px] font-bold tabular-nums {fact.dim
									? 'text-neutral-600'
									: 'text-neutral-800'}">{fact.value}</span
							>
						</div>
					{/each}
				</div>
			</div>

			<div class="f-cell flex flex-col gap-1.5">
				<div class="f-label">subject</div>
				{#if selfie}
					<img
						src={viewUrl(selfie)}
						alt="Instance {instance}"
						class="h-[104px] w-[78px] object-cover sm:h-[128px] sm:w-[96px]"
						onerror={(e) => fallback(e, selfie)}
					/>
				{:else}
					<span class="h-[104px] w-[78px] bg-neutral-300 sm:h-[128px] sm:w-[96px]"></span>
				{/if}
			</div>
		</div>

		<!-- The body: the register on the left, the plates on the right. -->
		<div class="mt-5 flex flex-col gap-[22px] md:flex-row">
			<div class="relative flex min-w-0 flex-1 flex-col gap-px">
				<section
					aria-label="The day"
					class="relative flex min-h-[340px] flex-1 flex-col"
					style="box-shadow: inset 0 0 0 1px var(--color-neutral-500)"
				>
					<!-- "the day" and not "record": the form's title already says
					     Record, and one sheet does not name two things alike. -->
					<div
						class="f-label flex h-7 shrink-0 items-center px-3.5"
						style="box-shadow: inset 0 -1px 0 0 var(--color-neutral-500)"
					>
						the day
					</div>
					{@render register()}
					{#if stamp}
						<!-- Stamped on the register when the Record was sealed. A
						     rotation is a transform, which is composited; nothing
						     here is a filter. -->
						<div
							aria-label="{stamp.label} at {stamp.time}"
							class="pointer-events-none absolute right-6 bottom-6 px-3.5 pt-[7px] pb-2 text-center"
							style="transform: rotate(-7deg); box-shadow: inset 0 0 0 2px var(--color-neutral-600); background: color-mix(in srgb, var(--color-sheet) 70%, transparent)"
						>
							<div class="text-[9px] font-extrabold tracking-[0.34em] text-neutral-700 uppercase">
								{stamp.label}
							</div>
							<div class="mt-[3px] text-[18px] font-extrabold tracking-[0.06em] text-neutral-800 tabular-nums">
								{stamp.time}
							</div>
						</div>
					{/if}
				</section>

				<div class="f-grid mt-[21px] grid-cols-1 sm:grid-cols-[minmax(0,1fr)_200px]">
					<div class="f-cell">
						<div class="f-label">on a scale of 1 to 10, how do you feel?</div>
						<div class="mt-2">{@render mood()}</div>
					</div>
					<div class="f-cell">
						<div class="f-label">signed</div>
						<div class="mt-1.5">{@render signed()}</div>
					</div>
				</div>

			</div>

			<aside aria-label="Plates" class="flex w-full shrink-0 flex-col gap-3.5 md:w-[330px]">
				<div class="flex h-7 items-baseline gap-2.5 pt-[9px]">
					<span class="f-label">plates</span>
					<span class="text-[11px] text-neutral-600 tabular-nums">{plateCount}</span>
					<span class="h-px flex-1 self-center bg-neutral-400"></span>
				</div>
				{@render plates()}

				<!-- What this sheet hands to the next one. -->
				<div class="mt-auto" style="box-shadow: inset 0 0 0 1px var(--color-neutral-500)">
					<div
						class="f-label flex items-baseline justify-between px-3 py-[7px]"
						style="box-shadow: inset 0 -1px 0 0 var(--color-neutral-500)"
					>
						<span>carried forward</span>
						<span class="tabular-nums">to {instance + 1}</span>
					</div>
					<div class="px-3 pt-2 pb-2.5">
						<div class="text-[11px] text-neutral-600">What do you want {instance + 1} to do?</div>
						{@render forward()}
					</div>
				</div>
			</aside>
		</div>

		<!-- The foot of the sheet. -->
		<div
			class="mt-3.5 flex h-[30px] items-center gap-4 text-[10px] tracking-[0.16em] text-neutral-600 uppercase tabular-nums"
		>
			{#if previous && prev}
				<span class="text-neutral-700">follows sheet {previous.instance} · {prev.date}</span>
			{:else}
				<span>first sheet</span>
			{/if}
			<span class="h-px flex-1 bg-neutral-400"></span>
		</div>
	</article>
</div>
