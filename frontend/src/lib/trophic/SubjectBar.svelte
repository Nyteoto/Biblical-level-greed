<script lang="ts">
	/**
	 * What you are looking at — the folder and the year, said once, in the shell.
	 *
	 * ## The half of the navigation that was missing
	 *
	 * The rail changes the **question**: Map, Log, Threads, Record. Nothing
	 * changed the **subject**, even though the subject is what all four are
	 * questions about and is the one thing that survives every switch. So the
	 * controls that set it ended up inside whichever lens needed them first —
	 * the folder in Map's chip row, the year in Map's year switcher — and two
	 * lenses never said which folder you were in at all.
	 *
	 * That is the bug this is: *"I thought clicking the folder brings me
	 * straight to log, but I forgot the step of choosing a folder first, which
	 * now can only be done via the Map's band of filter."* Choosing a folder is
	 * not a thing you do on Map.
	 *
	 * So: the rail is the question, this is the subject, and neither belongs to
	 * a lens. Changing either half here **keeps you where you are**, which is
	 * what makes them two axes rather than two kinds of travel.
	 *
	 * ## It is a line, not a column
	 *
	 * Forty pixels of height, on a screen whose lenses want every pixel of
	 * width — the year grid is twelve columns and the reading sheet is a sheet.
	 * It also means there is nothing to collapse, which is most of what made the
	 * old per-lens sidebars feel unpredictable: four columns, three different
	 * hide-widths, one of them guessing from the viewport.
	 *
	 * ## Capture has no subject
	 *
	 * And so does not get this. You have not written the line yet — the same
	 * reason the rail's Capture key carries no scope.
	 */
	import { page } from '$app/state';
	import { goto } from '$app/navigation';
	import { lensHref, readScope, thisYear } from './scope';
	import { subject } from './subject.svelte';
	import FolderPicker from './FolderPicker.svelte';

	const bar = subject();
	const scope = $derived(readScope(page.url));

	// The shelf is a year's, so the bar asks for the year in the URL. Every
	// lens under it reads the same store, so this is the only ask.
	$effect(() => {
		bar.want(scope.year);
	});

	/** What the folder is called. `All folders` and `Unfiled` are names like any
	 *  other — the two openings were a dashed card and a chip once, which made
	 *  them look like folders that had gone wrong. */
	const name = $derived.by(() => {
		if (!scope.folder) return 'All folders';
		if (scope.folder === 'unfiled') return 'Unfiled';
		return bar.data?.albums.find((a) => a.id === scope.folder)?.name ?? '…';
	});

	let years = $state(false);
	let anchor = $state<HTMLElement | null>(null);

	/** Where the picker hangs: under the name it is a list of. Measured from
	 *  the button rather than computed from the rail's width and the strip's
	 *  height, because both of those change and neither is this component's to
	 *  know. Read when the panel opens — a closed panel has no position worth
	 *  keeping current. */
	let at = $state({ x: 64, y: 96 });

	function openPicker() {
		const box = anchor?.getBoundingClientRect();
		if (box) at = { x: Math.round(box.left), y: Math.round(box.bottom + 4) };
		bar.toggle();
	}

	function pickYear(year: string) {
		years = false;
		goto(lensHref(page.url.pathname, { ...scope, year }), { noScroll: true, keepFocus: true });
	}
</script>

<div
	class="flex shrink-0 items-center gap-1 px-4 py-1.5 sm:px-[26px]"
	style="box-shadow:inset 0 -1px 0 0 var(--color-neutral-400)"
>
	<button
		bind:this={anchor}
		type="button"
		aria-haspopup="menu"
		aria-expanded={bar.picking}
		class="flex h-9 min-w-0 items-center gap-2 px-2 text-left transition-colors hover:bg-neutral-200"
		title="choose the folder"
		onclick={openPicker}
	>
		<span class="max-w-[46vw] truncate text-[15px] font-bold tracking-[-0.01em] sm:max-w-[34ch]">
			{name}
		</span>
		<svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="shrink-0 text-neutral-600" aria-hidden="true"><path d="m3 4.5 3 3 3-3" /></svg>
	</button>

	<div class="relative">
		<button
			type="button"
			aria-haspopup="menu"
			aria-expanded={years}
			class="flex h-9 items-center gap-2 px-2 text-[13px] text-neutral-700 tabular-nums transition-colors hover:bg-neutral-200 hover:text-ink"
			title="choose the year"
			onclick={() => (years = !years)}
		>
			{scope.year === 'all' ? 'All years' : scope.year}
			<svg width="9" height="9" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" class="shrink-0 text-neutral-600" aria-hidden="true"><path d="m3 4.5 3 3 3-3" /></svg>
		</button>

		{#if years}
			<!-- svelte-ignore a11y_click_events_have_key_events -->
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div class="fixed inset-0 z-[9500]" onclick={() => (years = false)}></div>
			<div
				class="absolute top-[calc(100%+4px)] left-0 z-[9600] flex min-w-[140px] flex-col bg-surface py-1.5 shadow-lg"
				style="animation:landing-fade-in 0.12s ease-out"
			>
				{#each bar.data?.years ?? [thisYear()] as y (y)}
					<button
						type="button"
						class="flex h-10 items-center px-4 text-left text-[14px] tabular-nums transition-colors {y ===
						scope.year
							? 'accent-fill font-bold'
							: 'hover:bg-neutral-200'}"
						onclick={() => pickYear(y)}
					>
						{y}
					</button>
				{/each}
				<!-- Every year at once. A real answer rather than an absent one, which
				     is why `year` is a string and `all` is one of its values. -->
				<button
					type="button"
					class="flex h-10 items-center px-4 text-left text-[14px] transition-colors {scope.year ===
					'all'
						? 'accent-fill font-bold'
						: 'text-neutral-700 hover:bg-neutral-200 hover:text-ink'}"
					onclick={() => pickYear('all')}
				>
					All years
				</button>
			</div>
		{/if}
	</div>
</div>

{#if bar.picking}
	<FolderPicker x={at.x} y={at.y} onclose={() => bar.close()} />
{/if}
