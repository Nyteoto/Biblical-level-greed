<script lang="ts">
	import { goto } from '$app/navigation';
	import { getDashboard } from '$lib/api';

	let empty = $state(false);

	$effect(() => {
		getDashboard().then((d) => {
			if (d.domains.length) goto(`/tree/${d.domains[0].id}`, { replaceState: true });
			else empty = true;
		});
	});
</script>

{#if empty}
	<div class="flex h-[60vh] flex-col items-center justify-center gap-3 text-center">
		<p class="text-sm text-stone-400">No domains yet.</p>
		<a
			href="/tree/new"
			class="rounded-sm border border-amber-500/60 px-4 py-2 text-[11px] tracking-[0.18em] text-amber-300 uppercase hover:bg-amber-500/10"
		>
			create the first one
		</a>
	</div>
{/if}
