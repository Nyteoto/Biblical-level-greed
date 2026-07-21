<script lang="ts">
	import { untrack } from 'svelte';
	import { Crepe } from '@milkdown/crepe';
	import '@milkdown/crepe/theme/common/style.css';
	import '@milkdown/crepe/theme/frame-dark.css';

	interface Props {
		value: string;
		/** Store one image and return its URL. Crepe owns the rest of the image
		 * experience — the picker, drag, paste, captions — and only needs this. */
		onupload: (file: File) => Promise<string>;
		/** Body typeface. Crepe reads it from CSS variables, so this is a live
		 * swap — nothing reloads and the document is untouched. */
		font?: FontChoice;
		onsave?: () => void;
	}

	export type FontChoice = 'sans' | 'serif' | 'mono';

	// System stacks only: the app is served off a machine that may be offline and
	// a webfont would be one more thing to ship and cache.
	const FONTS: Record<FontChoice, string> = {
		sans: 'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
		serif: 'ui-serif, Georgia, Cambria, "Times New Roman", serif',
		mono: 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace'
	};

	let { value = $bindable(), onupload, font = 'sans', onsave }: Props = $props();

	const fontStack = $derived(FONTS[font] ?? FONTS.sans);

	let host = $state<HTMLDivElement | null>(null);

	$effect(() => {
		const root = host;
		if (!root) return;
		let live = true;

		const crepe = new Crepe({
			root,
			// `untrack` is load-bearing. Reading `value` normally would make this
			// effect depend on it, so every keystroke would tear the editor down
			// and rebuild it — which is exactly what stole focus on space/Enter.
			defaultValue: untrack(() => value),
			featureConfigs: {
				[Crepe.Feature.Placeholder]: {
					text: 'Everything you have worked out about this node.',
					mode: 'doc'
				},
				[Crepe.Feature.ImageBlock]: {
					onUpload: onupload,
					blockOnUpload: onupload
				}
			}
		});

		crepe.on((api) => {
			api.markdownUpdated((_ctx, markdown) => {
				value = markdown;
			});
		});

		crepe.create().then(() => {
			if (!live) crepe.destroy();
		});

		return () => {
			live = false;
			crepe.destroy();
		};
	});

	// The editor mounts only after the note has loaded, so there is no reverse
	// sync: `value` flows out of here and nothing writes back into it. Fewer
	// moving parts than reconciling two copies of the same document.

	function keydown(event: KeyboardEvent) {
		if ((event.metaKey || event.ctrlKey) && event.key === 's') {
			event.preventDefault();
			onsave?.();
		}
	}
</script>

<div
	bind:this={host}
	onkeydown={keydown}
	class="crepe-host h-full w-full overflow-auto"
	style="--note-font: {fontStack}"
></div>

<style>
	/* Crepe ships its own dark theme; these are the few variables that make it
	   the app's dark rather than a generic one. */
	.crepe-host :global(.milkdown) {
		/* Set here, not on the host: Crepe's theme declares these on `.milkdown`
		   itself, so anything set further out loses the cascade. */
		--crepe-font-default: var(--note-font);
		--crepe-font-title: var(--note-font);
		--crepe-color-background: #14100c;
		--crepe-color-on-background: #d6d3d1;
		--crepe-color-surface: #171310;
		--crepe-color-surface-low: #1c1714;
		--crepe-color-on-surface: #e7e5e4;
		--crepe-color-on-surface-variant: #a8a29e;
		--crepe-color-outline: #44403c;
		--crepe-color-primary: #f59e0b;
		--crepe-color-secondary: #4a3a1a;
		--crepe-color-on-secondary: #fcd34d;
		--crepe-color-inverse: #e7e5e4;
		--crepe-color-on-inverse: #14100c;
		--crepe-color-inline-code: #fcd34d;
		--crepe-color-error: #f43f5e;
		--crepe-color-hover: rgba(245, 158, 11, 0.08);
		--crepe-color-selected: rgba(245, 158, 11, 0.18);
		--crepe-color-inline-area: rgba(245, 158, 11, 0.12);
		height: 100%;
	}
	.crepe-host :global(.milkdown .ProseMirror) {
		/* Crepe's frame theme leads with ~140px of air, which is a lot of nothing
		   above a note you opened to read. */
		padding-top: 1.5rem;
		/* Deep bottom padding: on iOS there has to be somewhere to tap below the
		   last block or the keyboard never comes up. */
		padding-bottom: max(8rem, env(safe-area-inset-bottom));
	}
	.crepe-host :global(.milkdown img) {
		max-height: 60vh;
	}

	/* Crepe's resize handle is 4px tall and only appears on :hover. A touch
	   screen has no hover, so on the iPad it was invisible and impossible to
	   grab. On a coarse pointer it stays visible and gets a real target. */
	@media (pointer: coarse) {
		.crepe-host :global(.milkdown .milkdown-image-block .image-wrapper .image-resize-handle) {
			background: transparent;
			bottom: -16px;
			height: 32px;
			max-width: 100%;
			opacity: 1;
			touch-action: none;
		}
		/* The visible grip, drawn inside the much larger touch target. */
		.crepe-host
			:global(.milkdown .milkdown-image-block .image-wrapper .image-resize-handle::after) {
			background: var(--crepe-color-outline);
			border-radius: 4px;
			content: '';
			height: 5px;
			left: 50%;
			position: absolute;
			top: 50%;
			transform: translate(-50%, -50%);
			width: 88px;
		}
		/* Same problem on the edit/caption controls: hover-only reveals never
		   fire, so keep them on. */
		.crepe-host :global(.milkdown .milkdown-image-block .image-wrapper .image-resize-handle:active::after) {
			background: var(--crepe-color-primary);
		}
	}
</style>
