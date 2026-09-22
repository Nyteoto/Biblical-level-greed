<script lang="ts">
	/**
	 * Everything you can change about a folder, opened where you held it.
	 *
	 * This used to be a dropdown behind a small button in the album header, and
	 * it was the only route to any of it: rename, lifecycle, which tags point
	 * here, delete. A screen you have to be *on* in order to rename the thing
	 * you are looking at is a screen doing navigation's job, so the button is
	 * gone and this opens from the folder wherever the folder is drawn — the
	 * year shelf's cards and the album sidebar's rows both.
	 *
	 * That is the whole argument for the hold gesture: the panel goes to the
	 * object rather than the object being carried to the panel. One component
	 * for both surfaces so the two can never drift into offering different
	 * powers over the same folder.
	 *
	 * Mapping a loose tag is in here for the same reason. It is the one edit
	 * that otherwise costs a trip to `/mapping`, and it is retroactive — point
	 * `<deploy>` here and every line ever written with it joins, with nothing
	 * migrated. Membership is resolved, never stored; this panel only ever moves
	 * the pointer.
	 *
	 * The group control is here for the third time on the same argument, with one
 * difference worth stating: a group is a fact about the folder *in one year*,
 * so this control only appears when a year is actually selected. On the
 * all-years shelf there is no year for a choice to be about, and offering the
 * control there would make the user pick a group that gets written to a year
 * they cannot see.
 *
 * The backdrop, the position and the rule that a hold's own release must not
	 * dismiss what it opened all live in `HoldMenu` — there are two of these
	 * panels now and those rules are subtle enough that a second copy would drift.
	 */
	import { toRamp } from './colors';
	import HoldMenu from './HoldMenu.svelte';
	import Segmented from './Segmented.svelte';
	import type { Folder, UnassignedTag } from './api';

	let {
		x,
		y,
		folder,
		unassigned = [],
		onpatch,
		ondelete,
		onclose,
		year = null,
		group = '',
		groups = [],
		ongroup
	}: {
		x: number;
		y: number;
		folder: Folder;
		unassigned?: UnassignedTag[];
		onpatch: (change: {
			name?: string;
			state?: string;
			add_tags?: string[];
			remove_tags?: string[];
		}) => void;
		ondelete: () => void;
		onclose: () => void;
		/** The shelf year this panel was opened over, or null on the all-years
		 *  shelf. Null hides the group control entirely — see the header. */
		year?: string | null;
		/** The folder's group in that year, and every group the year already
		 *  has. Both empty is the ordinary starting state. */
		group?: string;
		groups?: string[];
		ongroup?: (name: string) => void;
	} = $props();

	let renaming = $state(false);
	let renameValue = $state('');
	/** Naming a new group. Separate from `renaming` because both can be open
	 *  over the same panel and they are not the same edit. */
	let naming = $state(false);
	let nameValue = $state('');

	const canGroup = $derived(Boolean(ongroup && year && year !== 'all'));

	function submitGroup() {
		const next = nameValue.trim();
		naming = false;
		nameValue = '';
		if (!next || next === group) return;
		ongroup?.(next);
	}


	const STATES = [
		{ value: '', label: 'open' },
		{ value: 'active', label: 'running' },
		{ value: 'shipped', label: 'shipped' }
	];

	function submitRename() {
		const next = renameValue.trim();
		renaming = false;
		if (!next || next === folder.name) return;
		onpatch({ name: next });
	}
</script>

<HoldMenu {x} {y} {onclose}>
		{#if renaming}
			<form
				onsubmit={(e) => {
					e.preventDefault();
					submitRename();
				}}
			>
				<!-- svelte-ignore a11y_autofocus -->
				<input
					autofocus
					bind:value={renameValue}
					aria-label="folder name"
					class="w-full bg-neutral-200 px-3 py-2 text-[14px]"
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
						renameValue = folder.name;
						renaming = true;
					}}
				>
					<span
						class="h-2 w-2 shrink-0 self-center rounded-full"
						style="background:{toRamp(folder.color)}"
					></span>
					<span class="truncate">{folder.name}</span>
					<span class="shrink-0 text-[12px] font-normal text-neutral-700">rename</span>
				</button>
				<!-- The way out you can see. Tapping the backdrop works too, but a
				     panel whose only exit is "somewhere else" does not look closable. -->
				<button
					type="button"
					class="-mr-1 flex h-8 w-8 shrink-0 items-center justify-center text-[15px] text-neutral-700 transition-colors hover:bg-neutral-200 hover:text-ink"
					aria-label="close"
					onclick={onclose}
				>
					✕
				</button>
			</div>
		{/if}

		<!-- Three states and no taxonomy: the empty one is the default, and a
		     folder never marked is an interest rather than a project. -->
		<Segmented
			options={STATES}
			value={folder.state ?? ''}
			onpick={(state) => onpatch({ state })}
			label="this folder's state"
		/>

		{#if canGroup}
			<!-- Where this card sits on the shelf, this year. Cosmetic: it files
			     nothing and gates nothing, which is why it is a row of chips
			     rather than anything that looks like a decision. -->
			<div class="flex flex-col gap-2">
				<div class="flex items-baseline gap-2 text-[12px] text-neutral-700">
					<span class="font-semibold">Group</span>
					<span class="tabular-nums">{year}</span>
				</div>
				{#if naming}
					<form
						onsubmit={(e) => {
							e.preventDefault();
							submitGroup();
						}}
					>
						<!-- svelte-ignore a11y_autofocus -->
						<input
							autofocus
							bind:value={nameValue}
							maxlength="32"
							aria-label="new group name"
							placeholder="name the group"
							class="w-full bg-neutral-200 px-3 py-2 text-[14px]"
							onkeydown={(e) => {
								if (e.key === 'Escape') naming = false;
							}}
						/>
					</form>
				{:else}
					<div class="flex flex-wrap gap-1.5 text-[12px]">
						<button
							type="button"
							class=" px-2.5 py-1 transition-colors {group
								? 'text-neutral-700 hover:bg-neutral-200'
								: 'bg-neutral-200 font-semibold text-ink'}"
							onclick={() => ongroup?.('')}
						>
							none
						</button>
						{#each groups as name (name)}
							<button
								type="button"
								class="max-w-[140px] truncate px-2.5 py-1 transition-colors {name ===
								group
									? 'bg-neutral-200 font-semibold text-ink'
									: 'text-neutral-700 hover:bg-neutral-200'}"
								onclick={() => ongroup?.(name)}
							>
								{name}
							</button>
						{/each}
						<button
							type="button"
							class=" px-2.5 py-1 text-accent-700 transition-colors hover:bg-neutral-200"
							onclick={() => {
								nameValue = '';
								naming = true;
							}}
						>
							+ new
						</button>
					</div>
				{/if}
			</div>
		{/if}

		<!-- What points here. The mapping *is* the folder, so it is shown as the
		     definition rather than as a summary, and each tag is a button that
		     removes itself. -->
		<div class="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 text-[12px]">
			{#each folder.tags as tag (tag)}
				<button
					type="button"
					class="font-mono transition-colors hover:text-accent-700"
					style="color:var(--color-accent-700)"
					title="click to unmap"
					onclick={() => onpatch({ remove_tags: [tag] })}
				>
					{`<${tag}>`}
				</button>
			{:else}
				<span class="text-neutral-700">no tags point here yet</span>
			{/each}
		</div>

		{#if unassigned.length > 0}
			<!-- The loose tags, right here. This is the trip to the mapping screen
			     that the hold gesture exists to remove. -->
			<div class="flex flex-wrap gap-2 bg-neutral-200 p-2.5 text-[12px]">
				{#each unassigned.slice(0, 10) as tag (tag.tag)}
					<button
						type="button"
						class="font-mono transition-colors hover:opacity-70"
						style="color:var(--color-neutral-800)"
						title="point this tag here"
						onclick={() => onpatch({ add_tags: [tag.tag] })}
					>
						{`<${tag.tag}>`}<span class="ml-1 text-neutral-700">×{tag.count}</span>
					</button>
				{/each}
			</div>
		{/if}

	<button
		type="button"
		class="self-start text-[12px] font-semibold text-accent-700"
		onclick={ondelete}
	>
		Delete this folder
	</button>
</HoldMenu>
