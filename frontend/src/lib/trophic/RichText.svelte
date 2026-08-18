<script lang="ts">
	/**
	 * A small rich-text field: bold, italic, headings, lists, quotes.
	 *
	 * The source's editor was Milkdown Crepe and it left with the notes system,
	 * so there is nothing to port. This is deliberately not a replacement for it
	 * — an overview is a paragraph or three about a project, not a document, and
	 * a ProseMirror stack to hold that would be more code than the app it sits
	 * in.
	 *
	 * **It stores HTML, and sanitises on the way in and the way out.** The
	 * content is written by the one person who uses this app, on their own
	 * machine, so the threat model is not an attacker — it is a paste from a web
	 * page carrying a stylesheet, a font stack and a tracking pixel into a
	 * screen that is meant to be one hue. `clean()` keeps a small tag list and
	 * drops every attribute, which is also what keeps the phosphor consistent:
	 * nothing pasted can bring its own colour.
	 *
	 * Paste is intercepted for the same reason and inserted as plain text, so
	 * formatting comes from this toolbar and only from it.
	 *
	 * `execCommand` is deprecated and has no replacement for this job. The
	 * alternative is a selection-and-range implementation of the same six
	 * commands, which is a well-known source of subtle bugs and would be, again,
	 * more code than the feature. It works in every engine this app runs in.
	 */

	let {
		html = $bindable(''),
		placeholder = ''
	}: { html?: string; placeholder?: string } = $props();

	import { clean } from './richtext';

	let editor = $state<HTMLDivElement | null>(null);

	// Seeded once. Writing `innerHTML` on every change would move the caret to
	// the start on every keystroke, which is the classic way a contenteditable
	// bound to state becomes unusable.
	$effect(() => {
		const el = editor;
		if (!el || el.dataset.seeded) return;
		el.dataset.seeded = 'yes';
		el.innerHTML = html;
	});

	function sync() {
		if (editor) html = editor.innerHTML;
	}

	/**
	 * What is in the field right now, read from the element.
	 *
	 * Save reads this rather than trusting the binding. A contenteditable
	 * reports its content through `input` events, and anything that swallows,
	 * reorders or arrives after the click — an IME still composing, a compositor
	 * batching, a button that takes focus first — leaves the bound copy behind
	 * by exactly the characters most worth keeping. The element is the truth and
	 * it is one property read away; there is no reason for the button to ask
	 * anyone else.
	 */
	export function current(): string {
		return editor?.innerHTML ?? html;
	}

	// Pasted markup is cleaned when it lands rather than only when it saves, so
	// what you are looking at while you write is what will be kept.
	function scrub() {
		if (!editor) return;
		const kept = clean(editor.innerHTML);
		if (kept !== editor.innerHTML) editor.innerHTML = kept;
		html = editor.innerHTML;
	}

	function run(command: string, value?: string) {
		editor?.focus();
		document.execCommand(command, false, value);
		sync();
	}

	function onpaste(event: ClipboardEvent) {
		// Plain text only: formatting is this toolbar's to give.
		event.preventDefault();
		const text = event.clipboardData?.getData('text/plain') ?? '';
		document.execCommand('insertText', false, text);
		scrub();
	}

	const TOOLS: { label: string; title: string; run: () => void; bold?: boolean }[] = [
		{ label: 'B', title: 'bold', run: () => run('bold'), bold: true },
		{ label: 'I', title: 'italic', run: () => run('italic') },
		{ label: 'H', title: 'heading', run: () => run('formatBlock', 'h2') },
		{ label: '¶', title: 'plain paragraph', run: () => run('formatBlock', 'p') },
		{ label: '•', title: 'bulleted list', run: () => run('insertUnorderedList') },
		{ label: '1.', title: 'numbered list', run: () => run('insertOrderedList') },
		{ label: '❝', title: 'quote', run: () => run('formatBlock', 'blockquote') }
	];
</script>

<div class="flex min-h-0 flex-1 flex-col gap-2.5">
	<!-- The keys, in the same vocabulary as the capture bar's syntax row: a
	     glyph that does the thing rather than a word describing it. -->
	<div class="flex flex-wrap gap-1.5">
		{#each TOOLS as tool (tool.label)}
			<button
				type="button"
				class="lift lift-sm h-8 min-w-8 rounded-[9px] bg-surface px-2 text-[13px] shadow-sm {tool.bold
					? 'font-bold'
					: ''}"
				title={tool.title}
				onmousedown={(e) => e.preventDefault()}
				onclick={tool.run}
			>
				{tool.label}
			</button>
		{/each}
	</div>

	<!-- svelte-ignore a11y_no_static_element_interactions -->
	<div
		bind:this={editor}
		contenteditable="true"
		role="textbox"
		tabindex="0"
		aria-label="overview"
		data-placeholder={placeholder}
		class="prose-overview min-h-[220px] flex-1 overflow-y-auto rounded-[14px] bg-surface p-4 text-[14px] leading-[1.7] shadow-md"
		oninput={sync}
		{onpaste}
	></div>
</div>

<style>
	/* The empty state, without a second element to position over the field. */
	.prose-overview:empty::before {
		content: attr(data-placeholder);
		color: var(--color-neutral-700);
	}
</style>
