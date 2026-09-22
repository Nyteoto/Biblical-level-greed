<script lang="ts">
	import { toRamp } from './colors';
	/**
	 * The floating menu for filing an entry into a folder by hand.
	 * Ported from `components/FolderAssignMenu.tsx`.
	 *
	 * Three behaviours in it are not decoration:
	 *   - it clamps itself into the viewport after mounting, because it opens
	 *     at the pointer and the pointer is often near an edge;
	 *   - the search box is focused on a mouse but never on a touch screen,
	 *     where focusing it would throw the keyboard over the list it filters;
	 *   - the radio dot is the current filing, so the menu says where the
	 *     entry already is rather than only offering somewhere to put it.
	 *
	 * Queueing a todo is in here rather than behind a hold of its own. The row
	 * this opens from already answers a hold, and a gesture on the todo line
	 * inside it would open a second menu over the first. One hold, one menu,
	 * and the menu carries everything you can do to the line you held.
	 *
	 * There used to be a sharper reason: two hold mechanisms with two 500ms
	 * timers, either of which could fire. They are one action now — see
	 * `hold.ts` — so this is a rule about menus rather than about timers.
	 */
	import type { Folder } from './api';

	let {
		x,
		y,
		folders,
		current = null,
		onselect,
		onclear,
		onclose,
		todos = [],
		queued = null,
		onqueue
	}: {
		x: number;
		y: number;
		folders: Folder[];
		current?: string | null;
		onselect: (folderId: string) => void;
		onclear: () => void;
		onclose: () => void;
		/** This entry's still-open `--todo` lines, as `{line, text}`. Empty for
		 *  an entry with none, which is most of them. */
		todos?: { line: number; text: string }[];
		/** The line already queued on this device, if it is one of these. */
		queued?: number | null;
		onqueue?: (line: number) => void;
	} = $props();

	let menu = $state<HTMLDivElement | null>(null);
	let search = $state<HTMLInputElement | null>(null);
	// Capturing the initial position is the intent: the menu opens where the
	// pointer was, and a new open is a new instance of this component.
	// svelte-ignore state_referenced_locally
	let pos = $state({ x, y });
	let query = $state('');

	$effect(() => {
		const el = menu;
		if (!el) return;

		const box = el.getBoundingClientRect();
		const margin = 8;
		let nx = x;
		let ny = y;
		if (x + box.width + margin > window.innerWidth) nx = window.innerWidth - box.width - margin;
		if (y + box.height + margin > window.innerHeight) ny = window.innerHeight - box.height - margin;
		pos = { x: Math.max(nx, margin), y: Math.max(ny, margin) };

		if (!window.matchMedia('(pointer: coarse) and (hover: none)').matches) {
			const t = setTimeout(() => search?.focus(), 10);
			return () => clearTimeout(t);
		}
	});

	/**
	 * The moment it opened, and whether the tail of that gesture has been let
	 * through yet.
	 *
	 * This menu is opened by a hold, and a hold ends with a lift. On a touch
	 * screen the lift is followed by a synthetic `mousedown` at the same point
	 * — which is outside this menu, because the menu opened *over* where the
	 * finger was — and that closed it again before it had finished appearing.
	 * Hold, wait for the ring, see the menu, let go, watch it vanish.
	 *
	 * `HoldMenu` had already solved this for the folder panels by swallowing
	 * the first press after opening; this is the same fix, and the two should
	 * stay the same. It is written with a window rather than a plain flag so a
	 * deliberate press *later* still dismisses on the first go — only the press
	 * that arrives in the tail of the opening gesture is spent.
	 */
	const opened = Date.now();
	const TAIL = 700;
	let spent = false;

	function outside(event: Event) {
		if (!menu || menu.contains(event.target as Node)) return;
		if (!spent && Date.now() - opened < TAIL) {
			spent = true;
			return;
		}
		onclose();
	}

	const filtered = $derived(
		query.trim()
			? folders.filter((f) => f.name.toLowerCase().includes(query.trim().toLowerCase()))
			: folders
	);
</script>

<svelte:document onmousedown={outside} ontouchstart={outside} />
<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<div
	bind:this={menu}
	class="fixed z-[120] flex max-w-[260px] min-w-[200px] flex-col bg-surface py-2 shadow-lg"
	style="left:{pos.x}px;top:{pos.y}px;animation:landing-fade-in 0.12s ease-out"
>
	<div class="px-2.5 pb-2">
		<div class="px-1 pt-0.5 pb-2 text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">
			assign to folder
		</div>
		<input
			bind:this={search}
			bind:value={query}
			placeholder="search…"
			class="w-full bg-neutral-200 px-2.5 py-1.5 text-[12px]"
		/>
	</div>

	<div class="trophic-scrollbar-hide max-h-[220px] overflow-y-auto py-1">
		{#if folders.length === 0}
			<div class="px-3 py-2 text-[12px] text-neutral-700">no folders yet.</div>
		{:else if filtered.length === 0}
			<div class="px-3 py-2 text-[12px] text-neutral-700">no match.</div>
		{:else}
			{#each filtered as f (f.id)}
				{@const active = f.id === current}
				<button
					type="button"
					class="mx-1.5 flex items-center gap-2.5 px-2.5 py-1.5 text-left text-[13px] transition-colors {active
						? 'bg-neutral-200 font-semibold'
						: 'hover:bg-neutral-200'}"
					onclick={() => {
						onselect(f.id);
						onclose();
					}}
				>
					<span class="shrink-0" style="color:{toRamp(f.color)}">{active ? '●' : '○'}</span>
					<span class="truncate">{f.name}</span>
				</button>
			{/each}
		{/if}
	</div>

	{#if todos.length > 0 && onqueue}
		<!-- The banner shows one todo at a time, oldest first. This is how you
		     say "that one, next" — per device, written nowhere. Listed per line
		     rather than per entry, because a todo is a line and an entry can
		     carry several. -->
		<div class="mt-1 border-t border-neutral-300 px-1.5 pt-1.5">
			{#each todos as todo (todo.line)}
				<button
					type="button"
					class="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-[12px] transition-colors hover:bg-neutral-200 {todo.line ===
					queued
						? 'font-semibold text-accent-700'
						: 'text-neutral-700 hover:text-accent-700'}"
					onclick={() => {
						onqueue(todo.line);
						onclose();
					}}
				>
					<span class="shrink-0">{todo.line === queued ? '●' : '○'}</span>
					<span class="truncate">
						{todos.length > 1 ? todo.text : 'Queue next'}
					</span>
				</button>
			{/each}
		</div>
	{/if}

	{#if current}
		<div class="mt-1 px-1.5">
			<button
				type="button"
				class="w-full px-2.5 py-1.5 text-left text-[12px] text-neutral-700 transition-colors hover:bg-neutral-200 hover:text-accent-700"
				onclick={() => {
					onclear();
					onclose();
				}}
			>
				remove manual assignment
			</button>
		</div>
	{/if}
</div>
