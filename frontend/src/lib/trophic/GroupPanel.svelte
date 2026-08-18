<script lang="ts">
	/**
	 * What you can do to a shelf group, opened where you held its heading.
	 *
	 * The same argument as `FolderPanel`, applied to the other thing on this
	 * screen that is an object rather than a link: the panel goes to the group
	 * instead of the group being carried to a settings screen. A heading with a
	 * rename button and a delete button permanently beside it would be two
	 * controls sitting on screen forever to be used twice each, which is exactly
	 * what the hold gesture exists to delete.
	 *
	 * ## Delete says what it does, because the word is worse than the act
	 *
	 * A group has never held anything. Deleting one un-groups its folders and
	 * returns them to the loose grid above — no folder is deleted, no entry is
	 * touched, and the same thing could be done one card at a time. So there is
	 * no confirm dialog: a confirm on an action that loses nothing teaches you
	 * to dismiss confirms. What there is instead is a line saying where the
	 * folders go, which is the thing you actually want to know before pressing
	 * it.
	 *
	 * Renaming onto a name the year already uses merges the two groups. That is
	 * the obvious reading of the gesture and it is what the fold does anyway;
	 * the panel does not warn about it, because "these two are the same thing"
	 * is a legitimate thing to be saying.
	 *
	 * The backdrop, the position, and the rule that a hold's own release must
	 * not dismiss what it opened all live in `HoldMenu`.
	 */
	import HoldMenu from './HoldMenu.svelte';
	import Glyph from './Glyph.svelte';

	let {
		x,
		y,
		name,
		year,
		count,
		onrename,
		ondelete,
		onclose
	}: {
		x: number;
		y: number;
		name: string;
		/** The shelf year this group belongs to. Printed, because a group is a
		 *  per-year arrangement and the panel is the place that admits it. */
		year: string;
		/** How many folders sit under it — what the delete line is about. */
		count: number;
		onrename: (to: string) => void;
		ondelete: () => void;
		onclose: () => void;
	} = $props();

	let renaming = $state(false);
	let value = $state('');

	function submit() {
		const next = value.trim();
		renaming = false;
		if (!next || next === name) return;
		onrename(next);
	}
</script>

<HoldMenu {x} {y} {onclose}>
	{#if renaming}
		<form
			onsubmit={(e) => {
				e.preventDefault();
				submit();
			}}
		>
			<!-- svelte-ignore a11y_autofocus -->
			<input
				autofocus
				bind:value
				maxlength="32"
				aria-label="group name"
				class="w-full rounded-lg bg-neutral-200 px-3 py-2 text-[14px]"
				onkeydown={(e) => {
					if (e.key === 'Escape') renaming = false;
				}}
			/>
		</form>
	{:else}
		<div class="flex items-center gap-2">
			<button
				type="button"
				class="flex min-w-0 flex-1 items-baseline gap-2 text-left text-[14px] font-semibold"
				onclick={() => {
					value = name;
					renaming = true;
				}}
			>
				<span class="truncate">{name}</span>
				<span class="shrink-0 text-[12px] font-normal text-neutral-700">rename</span>
			</button>
			<!-- The way out you can see, as on the folder's panel. -->
			<button
				type="button"
				class="-mr-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[15px] text-neutral-700 transition-colors hover:bg-neutral-200 hover:text-ink"
				aria-label="close"
				onclick={onclose}
			>
				✕
			</button>
		</div>
	{/if}

	<div class="flex items-center gap-3 text-[12px] text-neutral-700">
		<span class="tabular-nums">{year}</span>
		<span class="flex items-center gap-1.5 tabular-nums">
			<Glyph kind="album" {count} size={12} />
			{count}
		</span>
	</div>

	<div class="flex flex-col gap-1.5">
		<button
			type="button"
			class="self-start text-[12px] font-semibold text-accent-700"
			onclick={ondelete}
		>
			Delete this group
		</button>
		<!-- Said here rather than in a confirm: this is what you want to know
		     before pressing it, and it costs nothing to read. -->
		<span class="text-[11px] leading-[1.5] text-neutral-700">
			{count === 1 ? 'Its folder returns' : 'Its folders return'} to the top of the shelf. Nothing
			written is deleted.
		</span>
	</div>
</HoldMenu>
