<script lang="ts">
	import MarkdownEditor, { type FontChoice } from './MarkdownEditor.svelte';
	import { getNote, saveNote, uploadMedia } from '$lib/api';

	interface Props {
		domainId: string;
		nodeId: string;
		nodeTitle: string;
		onclose: () => void;
	}

	let { domainId, nodeId, nodeTitle, onclose }: Props = $props();

	// WYSIWYG, via Milkdown's Crepe: the editor they ship, not primitives
	// assembled here. It brings the toolbar, the slash menu, block handles,
	// tables, code blocks and the whole image experience — picker, drag, paste,
	// captions — so this file only loads, saves, and supplies an upload function.
	//
	// The file on disk is still markdown: Crepe parses and serialises through
	// remark, so a note stays readable in any text editor, greppable, diffable,
	// and `media.py` can still append to it from outside the app. The cost is
	// that saving normalises formatting (`*` vs `_`, blank lines) to remark's
	// house style. Content survives; byte-for-byte layout does not.
	let text = $state('');
	let saved = $state('');
	let loading = $state(true);
	let busy = $state(false);
	let error = $state<string | null>(null);

	// Reading and writing want different faces, and which one is which is a
	// matter of taste that changes. Kept on the device, not in the note.
	const FONT_KEY = 'pgs.note-font';
	const FACES: FontChoice[] = ['sans', 'serif', 'mono'];
	let font = $state<FontChoice>('sans');

	$effect(() => {
		const saved = localStorage.getItem(FONT_KEY) as FontChoice | null;
		if (saved && FACES.includes(saved)) font = saved;
	});

	function cycleFont() {
		font = FACES[(FACES.indexOf(font) + 1) % FACES.length];
		localStorage.setItem(FONT_KEY, font);
	}

	const dirty = $derived(text !== saved);

	$effect(() => {
		let cancelled = false;
		loading = true;
		getNote(domainId, nodeId)
			.then((r) => {
				if (cancelled) return;
				text = r.text;
				saved = r.text;
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

	/** Store the image and hand back its URL. No domain or node: the editor puts
	 * the picture in the document itself, and letting the server append it too
	 * would land it in the note twice. */
	async function upload(file: File): Promise<string> {
		error = null;
		try {
			const shot = await uploadMedia(file);
			return shot.url;
		} catch (e) {
			error = (e as Error).message.replace(/^\d+[: ]+/, '');
			throw e;
		}
	}

	function close() {
		if (dirty && !confirm('Unsaved changes. Close anyway?')) return;
		onclose();
	}

	function keydown(event: KeyboardEvent) {
		if ((event.metaKey || event.ctrlKey) && event.key === 's') {
			event.preventDefault();
			save();
		}
		if (event.key === 'Escape' && !dirty) onclose();
	}
</script>

<svelte:window onkeydown={keydown} />

<div class="fixed inset-0 z-50 flex flex-col bg-[#14100c]">
	<header
		class="flex shrink-0 flex-wrap items-center gap-2 border-b border-black/60 px-4 py-2.5"
		style="padding-top: max(0.625rem, env(safe-area-inset-top))"
	>
		<button
			onclick={close}
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

		<button
			onclick={cycleFont}
			title="Typeface: {font}"
			class="rounded-sm border border-stone-800 px-2.5 py-1 text-[10px] tracking-[0.16em] text-stone-500 uppercase transition hover:border-stone-700 hover:text-stone-300"
		>
			{font}
		</button>

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

	<div class="min-h-0 flex-1 overflow-hidden">
		{#if loading}
			<p class="p-6 text-[13px] text-stone-600">loading…</p>
		{:else}
			<MarkdownEditor bind:value={text} {font} onupload={upload} onsave={save} />
		{/if}
	</div>
</div>
