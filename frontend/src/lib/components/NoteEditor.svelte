<script lang="ts">
	import { marked } from 'marked';
	import { getNote, saveNote } from '$lib/api';

	interface Props {
		domainId: string;
		nodeId: string;
		nodeTitle: string;
		onclose: () => void;
	}

	let { domainId, nodeId, nodeTitle, onclose }: Props = $props();

	// Markdown, not a block editor's JSON. Storage decisions are permanent and
	// which editor renders them is not — this file stays readable in any text
	// editor, greppable, and diffable by git.
	let text = $state('');
	let saved = $state('');
	let loading = $state(true);
	let busy = $state(false);
	let error = $state<string | null>(null);
	let mode = $state<'write' | 'read'>('write');
	let area = $state<HTMLTextAreaElement | null>(null);

	const dirty = $derived(text !== saved);
	const rendered = $derived(marked.parse(text || '_Empty._', { async: false }) as string);

	$effect(() => {
		let cancelled = false;
		loading = true;
		getNote(domainId, nodeId)
			.then((r) => {
				if (cancelled) return;
				text = r.text;
				saved = r.text;
				// An empty note opens ready to type; one with content opens
				// readable, because you are far more often consulting it.
				mode = r.text.trim() ? 'read' : 'write';
			})
			.catch((e) => !cancelled && (error = (e as Error).message))
			.finally(() => !cancelled && (loading = false));
		return () => (cancelled = true);
	});

	async function save() {
		if (busy || !dirty) return;
		busy = true;
		error = null;
		try {
			const r = await saveNote(domainId, nodeId, text);
			saved = r.text;
		} catch (e) {
			error = (e as Error).message.replace(/^\d+ [^:]+: /, '');
		} finally {
			busy = false;
		}
	}

	function keydown(event: KeyboardEvent) {
		if ((event.metaKey || event.ctrlKey) && event.key === 's') {
			event.preventDefault();
			save();
		}
		if (event.key === 'Escape' && !dirty) onclose();
	}

	/** Wrap or insert around the cursor — the two bits of formatting worth a
	 * button on a touch screen, where typing backticks is miserable. */
	function wrap(before: string, after = before) {
		const el = area;
		if (!el) return;
		const [s, e] = [el.selectionStart, el.selectionEnd];
		text = text.slice(0, s) + before + text.slice(s, e) + after + text.slice(e);
		queueMicrotask(() => {
			el.focus();
			el.selectionStart = s + before.length;
			el.selectionEnd = e + before.length;
		});
	}
</script>

<svelte:window onkeydown={keydown} />

<div class="fixed inset-0 z-50 flex flex-col bg-[#14100c]">
	<header
		class="flex shrink-0 flex-wrap items-center gap-2 border-b border-black/60 px-4 py-2.5"
		style="padding-top: max(0.625rem, env(safe-area-inset-top))"
	>
		<button
			onclick={onclose}
			class="text-[11px] tracking-[0.16em] text-stone-500 uppercase hover:text-stone-300"
		>
			← back
		</button>
		<div class="min-w-0 flex-1">
			<div class="truncate text-[13px] text-stone-200">{nodeTitle}</div>
			<div class="font-mono text-[10px] text-stone-600">
				notes · {domainId}/{nodeId}.md
			</div>
		</div>

		<div class="flex overflow-hidden rounded-sm border border-stone-800">
			{#each ['write', 'read'] as m (m)}
				<button
					onclick={() => (mode = m as 'write' | 'read')}
					class="px-3 py-1 text-[10px] tracking-[0.16em] uppercase transition
					{mode === m ? 'bg-amber-500/15 text-amber-300' : 'text-stone-500 hover:text-stone-300'}"
				>
					{m}
				</button>
			{/each}
		</div>

		<button
			onclick={save}
			disabled={busy || !dirty}
			class="rounded-sm border border-amber-500/60 px-3 py-1 text-[10px] tracking-[0.16em] text-amber-300 uppercase transition hover:bg-amber-500/10 disabled:border-stone-800 disabled:text-stone-600"
		>
			{busy ? 'saving…' : dirty ? 'save' : 'saved'}
		</button>
	</header>

	{#if error}
		<div class="border-b border-rose-500/40 bg-rose-500/10 px-4 py-2 text-[12px] text-rose-200">
			{error}
		</div>
	{/if}

	{#if mode === 'write'}
		<!-- Formatting bar: on a touch screen typing markdown punctuation is the
		     worst part, so the handful that matter get a button. -->
		<div class="flex shrink-0 gap-1 overflow-x-auto border-b border-black/40 px-3 py-1.5">
			{#each [['# ', 'H'], ['**', 'B'], ['_', 'I'], ['`', '‹›'], ['- ', '•'], ['> ', '❝']] as [ins, label] (label)}
				<button
					onclick={() => wrap(ins, ins.endsWith(' ') ? '' : ins)}
					class="shrink-0 rounded-sm border border-stone-800 px-2.5 py-1 font-mono text-[11px] text-stone-400 hover:border-stone-700 hover:text-stone-200"
				>
					{label}
				</button>
			{/each}
			<span class="ml-auto shrink-0 self-center pr-1 font-mono text-[10px] text-stone-700">
				markdown · ⌘S
			</span>
		</div>
	{/if}

	<div class="min-h-0 flex-1 overflow-auto">
		{#if loading}
			<p class="p-6 text-[13px] text-stone-600">loading…</p>
		{:else if mode === 'write'}
			<textarea
				bind:this={area}
				bind:value={text}
				spellcheck="true"
				placeholder={'Everything you have worked out about this node.\n\nMarkdown. Photos sent from the iPad land here automatically.'}
				class="h-full w-full resize-none bg-transparent px-5 py-4 font-mono text-[13px] leading-relaxed text-stone-200 placeholder:text-stone-700 focus:outline-none"
				style="padding-bottom: max(1rem, env(safe-area-inset-bottom))"
			></textarea>
		{:else}
			<!-- eslint-disable-next-line svelte/no-at-html-tags -->
			<article class="note-body mx-auto max-w-3xl px-5 py-5">{@html rendered}</article>
		{/if}
	</div>
</div>

<style>
	/* Scoped so it cannot leak into the rest of the app. The content is your
	   own markdown, rendered locally — there is no third party writing here. */
	.note-body :global(h1),
	.note-body :global(h2),
	.note-body :global(h3) {
		color: #e7e5e4;
		font-weight: 600;
		line-height: 1.25;
		margin: 1.4em 0 0.5em;
	}
	.note-body :global(h1) {
		font-size: 1.35rem;
	}
	.note-body :global(h2) {
		font-size: 1.15rem;
	}
	.note-body :global(h3) {
		font-size: 1rem;
	}
	.note-body :global(p),
	.note-body :global(li) {
		color: #a8a29e;
		font-size: 0.875rem;
		line-height: 1.7;
	}
	.note-body :global(ul),
	.note-body :global(ol) {
		margin: 0.6em 0;
		padding-left: 1.3em;
	}
	.note-body :global(ul) {
		list-style: disc;
	}
	.note-body :global(ol) {
		list-style: decimal;
	}
	.note-body :global(a) {
		color: #fcd34d;
		text-decoration: underline;
		text-underline-offset: 3px;
	}
	.note-body :global(code) {
		background: rgba(0, 0, 0, 0.4);
		border: 1px solid #292524;
		border-radius: 2px;
		font-size: 0.8rem;
		padding: 0.1em 0.35em;
	}
	.note-body :global(pre) {
		background: rgba(0, 0, 0, 0.4);
		border: 1px solid #292524;
		border-radius: 2px;
		overflow-x: auto;
		padding: 0.8em 1em;
	}
	.note-body :global(pre code) {
		background: none;
		border: 0;
		padding: 0;
	}
	.note-body :global(blockquote) {
		border-left: 2px solid #44403c;
		color: #78716c;
		margin: 0.8em 0;
		padding-left: 1em;
	}
	/* The whole point of the photo import: pictures you can actually look at. */
	.note-body :global(img) {
		border: 1px solid #292524;
		border-radius: 3px;
		display: block;
		height: auto;
		margin: 1em 0;
		max-width: 100%;
	}
	.note-body :global(hr) {
		border: 0;
		border-top: 1px solid #292524;
		margin: 1.5em 0;
	}
	.note-body :global(table) {
		border-collapse: collapse;
		font-size: 0.82rem;
		width: 100%;
	}
	.note-body :global(th),
	.note-body :global(td) {
		border-bottom: 1px solid #292524;
		padding: 0.4em 0.6em;
		text-align: left;
	}
</style>
