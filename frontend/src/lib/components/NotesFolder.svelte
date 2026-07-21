<script lang="ts">
	import NoteEditor from './NoteEditor.svelte';
	import { createNote, deleteNote, listNotes, type NoteSummary } from '$lib/api';

	interface Props {
		domainId: string;
		domainTitle: string;
		onclose: () => void;
	}

	let { domainId, domainTitle, onclose }: Props = $props();

	// One folder per domain, holding freely titled documents. There is no longer
	// a journal/note distinction: the thing you write at the end of a session is
	// both, and the app stopped asking which.
	let notes = $state<NoteSummary[]>([]);
	let loading = $state(true);
	let error = $state<string | null>(null);
	let busy = $state(false);
	let open = $state<NoteSummary | null>(null);

	async function load() {
		loading = true;
		try {
			notes = (await listNotes(domainId)).notes;
			error = null;
		} catch (e) {
			error = (e as Error).message;
		} finally {
			loading = false;
		}
	}

	$effect(() => {
		domainId;
		load();
	});

	async function make() {
		const title = prompt('Title this one:');
		if (!title?.trim() || busy) return;
		busy = true;
		try {
			const res = await createNote(domainId, title.trim());
			notes = res.notes;
			open = notes.find((n) => n.slug === res.slug) ?? null;
		} catch (e) {
			error = (e as Error).message.replace(/^\d+ [^:]+: /, '');
		} finally {
			busy = false;
		}
	}

	async function drop(note: NoteSummary) {
		if (!confirm(`Delete "${note.title}"? The file is removed from disk.`)) return;
		busy = true;
		try {
			notes = (await deleteNote(domainId, note.slug)).notes;
		} catch (e) {
			error = (e as Error).message.replace(/^\d+ [^:]+: /, '');
		} finally {
			busy = false;
		}
	}

	const when = (epoch: number) =>
		new Date(epoch * 1000).toLocaleDateString([], { day: 'numeric', month: 'short' });
</script>

<div class="fixed inset-0 z-40 flex flex-col bg-[#14100c]">
	<header
		class="flex shrink-0 items-center gap-3 border-b border-black/60 px-4 py-2.5"
		style="padding-top: max(0.625rem, env(safe-area-inset-top))"
	>
		<button
			onclick={onclose}
			class="text-[11px] tracking-[0.16em] text-stone-500 uppercase hover:text-stone-300"
		>
			← back
		</button>
		<div class="min-w-0 flex-1">
			<div class="truncate font-serif text-[15px] tracking-[0.1em] text-stone-200 italic">
				{domainTitle}
			</div>
			<div class="font-mono text-[10px] text-stone-600">
				{notes.length}
				{notes.length === 1 ? 'document' : 'documents'} · data/notes/{domainId}/
			</div>
		</div>
		<button
			onclick={make}
			disabled={busy}
			class="rounded-sm border border-amber-500/60 px-3 py-1 text-[10px] tracking-[0.16em] text-amber-300 uppercase transition hover:bg-amber-500/10 disabled:opacity-40"
		>
			new
		</button>
	</header>

	{#if error}
		<div class="border-b border-rose-500/40 bg-rose-500/10 px-4 py-2 text-[12px] text-rose-200">
			{error}
		</div>
	{/if}

	<div class="min-h-0 flex-1 overflow-y-auto">
		{#if loading}
			<p class="p-6 text-[13px] text-stone-600">loading…</p>
		{:else if !notes.length}
			<p class="mx-auto max-w-md p-8 text-center text-[13px] leading-relaxed text-stone-600">
				Nothing written here yet. One folder per domain — session notes, working
				problems, what you tried and what it taught you. All the same kind of thing.
			</p>
		{:else}
			<ul class="mx-auto max-w-3xl divide-y divide-stone-800/60 px-4 py-2">
				{#each notes as note (note.slug)}
					<li class="group flex items-center gap-3 py-2.5">
						<button onclick={() => (open = note)} class="min-w-0 flex-1 text-left">
							<div class="truncate text-[13px] text-stone-200 group-hover:text-white">
								{note.title}
							</div>
							{#if note.preview}
								<div class="truncate text-[11px] text-stone-600">{note.preview}</div>
							{/if}
						</button>
						<span class="shrink-0 font-mono text-[10px] text-stone-700">
							{when(note.updated)}
						</span>
						<button
							onclick={() => drop(note)}
							disabled={busy}
							class="shrink-0 text-[11px] text-stone-800 transition hover:text-rose-400"
							aria-label="Delete {note.title}"
						>
							✕
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</div>
</div>

{#if open}
	<NoteEditor
		{domainId}
		slug={open.slug}
		title={open.title}
		onclose={() => {
			open = null;
			load();
		}}
	/>
{/if}
