<script lang="ts">
	/** Trophic's shell inside the tech tree's tab bar.
	 *
	 * An app in an app: everything below this point is Trophic's layout and
	 * Trophic's interaction rules, and the only thing the host contributes is
	 * the tab strip above and the palette. The `.trophic` class is what scopes
	 * the reduced-motion rule and keeps the two products' CSS apart. */
	import '$lib/trophic/trophic.css';

	let { children } = $props();
</script>

<div class="trophic flex flex-col" style="min-height:var(--content-height)">
	{@render children()}
</div>
