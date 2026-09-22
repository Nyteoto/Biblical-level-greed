<script lang="ts">
	/**
	 * The shell every hold-opened panel sits in: a backdrop, a position, and the
	 * one rule that makes a panel opened by a finger usable at all.
	 *
	 * **The click that opened it must not close it.** These appear at 500ms with
	 * the finger still down, so the release fires a click straight onto the
	 * backdrop that has just appeared underneath. The panel is *armed* by that
	 * click rather than closed by it, and the click is stopped in the capture
	 * phase so it reaches nothing inside either — a release is not a choice, and
	 * letting it through would activate whichever option happened to sit under
	 * the finger. A 600ms floor arms it regardless, for the touch case where a
	 * long press may produce no click at all; a swallow flag left set eats the
	 * user's next real tap, which `long_press.json` already had to learn once.
	 *
	 * Arming on the click and not on a timer: the first version of this swallowed
	 * by elapsed time, and the release landed on the *panel* rather than the
	 * backdrop, so the budget went unspent and ate the user's next real click.
	 *
	 * **Clamped from the props, never from its own position.** An effect that
	 * reads the value it also writes re-triggers itself, and Svelte answers a
	 * self-feeding effect by tearing the component's reactivity down — which
	 * presents as a panel that renders perfectly and then ignores Escape, the
	 * backdrop and its own close button equally.
	 *
	 * **A panel opened by a *click* has nothing to absorb, and must say so.**
	 * All of that is about a press that is still down when the panel appears.
	 * Record opens the chapter panel from an ordinary click on a row — that
	 * click is over before this component exists, so the next one is the user's
	 * real choice and swallowing it makes the first press of every option do
	 * nothing. `armed` starts true in that case, and the caller is the only
	 * thing that knows which gesture it was.
	 *
	 * It exists so those paragraphs are true in one place. There are three
	 * panels in this shell now and there will be more.
	 */
	import type { Snippet } from 'svelte';

	let {
		x,
		y,
		width = 290,
		armed: openArmed = false,
		onclose,
		children
	}: {
		x: number;
		y: number;
		/** True when a click opened this rather than a hold — see the header.
		 *  There is no release to absorb, so the next click is a real choice. */
		armed?: boolean;
		/** The panel's width, in pixels. Fixed rather than intrinsic because these
		 *  open under a finger: a menu that changes width with its longest line
		 *  moves under the thumb already reaching for it. */
		width?: number;
		onclose: () => void;
		children: Snippet;
	} = $props();

	let panel = $state<HTMLDivElement | null>(null);
	// Capturing the initial position is the intent: it opens where the hold was,
	// and a new hold is a new instance of this component.
	// svelte-ignore state_referenced_locally
	let pos = $state({ x, y });
	// svelte-ignore state_referenced_locally
	let armed = $state(openArmed);

	$effect(() => {
		const el = panel;
		if (!el) return;
		const box = el.getBoundingClientRect();
		const margin = 12;
		const nx = Math.min(x, window.innerWidth - width - margin);
		const ny = Math.min(y, window.innerHeight - box.height - margin);
		pos = { x: Math.max(margin, nx), y: Math.max(margin, ny) };
	});

	$effect(() => {
		const arm = (event: MouseEvent) => {
			if (armed) return;
			armed = true;
			event.stopPropagation();
			event.preventDefault();
		};
		window.addEventListener('click', arm, true);
		const floor = setTimeout(() => (armed = true), 600);
		return () => {
			window.removeEventListener('click', arm, true);
			clearTimeout(floor);
		};
	});

	function onkeydown(event: KeyboardEvent) {
		if (event.key !== 'Escape') return;
		event.preventDefault();
		onclose();
	}
</script>

<svelte:window {onkeydown} />

<!-- svelte-ignore a11y_click_events_have_key_events -->
<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	class="fixed inset-0 z-[9700]"
	onclick={() => armed && onclose()}
	oncontextmenu={(e) => {
		e.preventDefault();
		if (armed) onclose();
	}}
>
	<!-- svelte-ignore a11y_click_events_have_key_events -->
	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		bind:this={panel}
		class="absolute flex flex-col gap-3 bg-surface p-4 shadow-lg"
		style="left:{pos.x}px; top:{pos.y}px; width:{width}px; animation:landing-fade-in 0.15s ease-out"
		onclick={(e) => e.stopPropagation()}
	>
		{@render children()}
	</div>
</div>
