<script lang="ts">
	import type { Snippet } from 'svelte';

	interface Props {
		title: string;
		subtitle?: string;
		submitLabel?: string;
		busy?: boolean;
		error?: string | null;
		onsubmit: () => void;
		oncancel: () => void;
		children: Snippet;
	}

	let {
		title,
		subtitle = '',
		submitLabel = 'save',
		busy = false,
		error = null,
		onsubmit,
		oncancel,
		children
	}: Props = $props();

	function onkeydown(event: KeyboardEvent) {
		if (event.key === 'Escape') oncancel();
	}
</script>

<svelte:window {onkeydown} />

<!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
<div
	class="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/70 p-6 backdrop-blur-sm"
	onclick={(e) => e.target === e.currentTarget && oncancel()}
>
	<form
		onsubmit={(e) => {
			e.preventDefault();
			onsubmit();
		}}
		class="my-auto w-full max-w-lg rounded-sm border border-stone-700 bg-gradient-to-b from-[#1e1811] to-[#141110] shadow-2xl"
	>
		<header class="border-b border-black/50 px-5 py-3.5">
			<h2 class="text-[12px] font-semibold tracking-[0.2em] text-stone-200 uppercase">
				{title}
			</h2>
			{#if subtitle}
				<p class="mt-1 text-[11px] text-stone-500">{subtitle}</p>
			{/if}
		</header>

		<div class="space-y-4 px-5 py-4">
			{@render children()}
		</div>

		{#if error}
			<p
				class="mx-5 mb-3 rounded-sm border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-[11px] text-rose-200"
			>
				{error}
			</p>
		{/if}

		<footer class="flex justify-end gap-2 border-t border-black/50 px-5 py-3">
			<button
				type="button"
				onclick={oncancel}
				class="rounded-sm border border-stone-800 px-3 py-1.5 text-[11px] tracking-[0.16em] text-stone-500 uppercase hover:text-stone-300"
			>
				cancel
			</button>
			<button
				type="submit"
				disabled={busy}
				class="rounded-sm border border-amber-500/60 px-4 py-1.5 text-[11px] tracking-[0.16em] text-amber-300 uppercase hover:bg-amber-500/10 disabled:opacity-40"
			>
				{busy ? '…' : submitLabel}
			</button>
		</footer>
	</form>
</div>
