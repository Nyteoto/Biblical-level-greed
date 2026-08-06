<script lang="ts">
	import { addTool, deleteTool, listTools, patchTool, uploadMedia, type Tool } from '$lib/api';

	interface Props {
		domainId: string;
		/** Domain accent, so the shelf reads as belonging to this tree. */
		tone?: string;
		accent?: string;
		glow?: string;
	}

	let {
		domainId,
		tone = 'text-amber-300',
		accent = 'border-amber-400/70',
		glow = ''
	}: Props = $props();

	// Collapsed by default, and deliberately not opened by navigation: arriving
	// at a tree is about the work, not the kit. You open this when you are
	// thinking about the kit.
	let open = $state(false);
	let tools = $state<Tool[]>([]);
	let error = $state<string | null>(null);
	let busy = $state(false);
	let editing = $state<Tool | null>(null);
	let picker = $state<HTMLInputElement | null>(null);
	let uploadFor = $state<string | null>(null);

	async function load() {
		try {
			tools = (await listTools(domainId)).tools;
			error = null;
		} catch (e) {
			error = (e as Error).message;
		}
	}

	$effect(() => {
		domainId;
		load();
	});

	function fail(e: unknown) {
		error = (e as Error).message.replace(/^\d+ [^:]+: /, '');
	}

	async function make() {
		const name = prompt('What is it called?');
		if (!name?.trim() || busy) return;
		busy = true;
		try {
			tools = (await addTool(domainId, { name: name.trim() })).tools;
		} catch (e) {
			fail(e);
		} finally {
			busy = false;
		}
	}

	async function save(tool: Tool, fields: Partial<Tool>) {
		busy = true;
		try {
			tools = (await patchTool(domainId, tool.id, fields)).tools;
			editing = tools.find((t) => t.id === tool.id) ?? null;
		} catch (e) {
			fail(e);
		} finally {
			busy = false;
		}
	}

	async function drop(tool: Tool) {
		if (!confirm(`Delete "${tool.name}"? Retiring keeps it on the shelf; this does not.`)) return;
		busy = true;
		try {
			tools = (await deleteTool(domainId, tool.id)).tools;
			editing = null;
		} catch (e) {
			fail(e);
		} finally {
			busy = false;
		}
	}

	/** Take the picture where the tool is. On iOS the file input opens the
	 * camera directly, which is the whole reason this is a plain input. */
	async function shoot(event: Event) {
		const input = event.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		const id = uploadFor;
		input.value = '';
		uploadFor = null;
		if (!file || !id) return;
		const tool = tools.find((t) => t.id === id);
		if (!tool) return;
		busy = true;
		try {
			const shot = await uploadMedia(file);
			tools = (await patchTool(domainId, id, { image: shot.url })).tools;
			editing = tools.find((t) => t.id === id) ?? null;
		} catch (e) {
			fail(e);
		} finally {
			busy = false;
		}
	}

	const today = () => new Date().toISOString().slice(0, 10);
	const live = $derived(tools.filter((t) => !t.retired));
	const retired = $derived(tools.filter((t) => t.retired));
</script>

<input bind:this={picker} onchange={shoot} type="file" accept="image/*" capture class="hidden" />

<!-- Docked to the bottom of the tree, over the empty half of the canvas. -->
<div class="pointer-events-none absolute inset-x-0 bottom-0 z-20 flex flex-col items-start">
	<button
		onclick={() => (open = !open)}
		class="pointer-events-auto ml-3 flex items-center gap-2.5 rounded-t-md border border-b-0 {accent} bg-[#171310] px-4 py-2 text-[11px] tracking-[0.18em] uppercase transition hover:bg-white/5 {tone} {open ? '' : glow}"
	>
		<!-- The icon carries the domain's colour: the shelf is per-domain, and the
		     tab is the only part of it visible most of the time. -->
		<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" class="h-4 w-4">
			<path d="M14.7 6.3a4 4 0 0 0 5 5L15 16l-3-3 2.7-6.7Z" stroke-linejoin="round" />
			<path d="M12 13 5 20a1.8 1.8 0 0 1-2.5-2.5L9.5 10" stroke-linecap="round" />
		</svg>
		<span>tools</span>
		{#if tools.length}
			<span class="rounded-full bg-white/10 px-1.5 font-mono text-[10px]">{live.length}</span>
		{/if}
		<span class="opacity-60">{open ? '▾' : '▴'}</span>
	</button>

	{#if open}
		<div
			class="pointer-events-auto w-full border-t border-stone-800 bg-[#171310]/95 px-4 py-4 backdrop-blur-sm"
		>
			{#if error}
				<p class="mb-2 text-[11px] text-rose-300">{error}</p>
			{/if}

			<div class="flex items-stretch gap-3 overflow-x-auto pb-1">
				{#each [...live, ...retired] as tool (tool.id)}
					<button
						onclick={() => (editing = tool)}
						class="group w-[164px] shrink-0 text-left {tool.retired ? 'opacity-45' : ''}"
					>
						<div
							class="flex h-[124px] w-full items-center justify-center overflow-hidden rounded-sm border border-stone-800 bg-black/40 transition group-hover:border-stone-700"
						>
							{#if tool.image}
								<img src={tool.image} alt={tool.name} class="h-full w-full object-cover" />
							{:else}
								<span class="text-[10px] tracking-[0.14em] text-stone-700 uppercase">
									no photo
								</span>
							{/if}
						</div>
						<!-- Serif and italic: a tool is a named object, not a label in the UI. -->
						<div class="mt-1.5 truncate font-serif text-[14px] text-stone-200 italic">
							{tool.name}
						</div>
						{#if tool.type}
							<div class="truncate font-mono text-[9px] text-stone-600">{tool.type}</div>
						{/if}
						{#if tool.retired}
							<div class="font-mono text-[9px] text-stone-700">retired</div>
						{/if}
					</button>
				{/each}

				<button
					onclick={make}
					disabled={busy}
					class="flex h-[124px] w-[164px] shrink-0 items-center justify-center rounded-sm border border-dashed border-stone-800 text-[11px] tracking-[0.16em] text-stone-700 uppercase transition hover:border-amber-500/50 hover:text-amber-400/80 disabled:opacity-40"
				>
					+ tool
				</button>
			</div>
		</div>
	{/if}
</div>

{#if editing}
	{@const tool = editing}
	<!-- The tree behind goes soft, so the object is the only thing in focus. -->
	<div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-md">
		<button
			onclick={() => (editing = null)}
			class="absolute inset-0 cursor-default"
			aria-label="Close"
		></button>

		<div
			class="relative max-h-[90dvh] w-full max-w-2xl overflow-y-auto rounded-sm border border-stone-800 bg-[#171310] shadow-2xl"
		>
			<div class="flex items-start gap-4 border-b border-stone-800 p-5">
				<button
					onclick={() => {
						uploadFor = tool.id;
						picker?.click();
					}}
					class="h-[164px] w-[164px] shrink-0 overflow-hidden rounded-sm border border-stone-800 bg-black/40 transition hover:border-stone-600"
					title="Take a photo of it"
				>
					{#if tool.image}
						<img src={tool.image} alt={tool.name} class="h-full w-full object-cover" />
					{:else}
						<span class="text-[10px] tracking-[0.14em] text-stone-600 uppercase">photo</span>
					{/if}
				</button>

				<div class="flex min-w-0 flex-1 flex-col self-stretch">
					<input
						value={tool.name}
						onchange={(e) => save(tool, { name: e.currentTarget.value })}
						placeholder="name it"
						class="w-full bg-transparent font-serif text-[24px] leading-tight text-stone-100 italic placeholder:text-stone-700 focus:outline-none"
					/>
					<p class="mt-0.5 font-mono text-[10px] text-stone-600">
						{tool.retired ? `retired ${tool.retired}` : 'in service'}
					</p>
					<!-- Beside the photo on purpose: what the thing is, in your words,
					     read together with the picture of it. -->
					<textarea
						value={tool.description}
						onchange={(e) => save(tool, { description: e.currentTarget.value })}
						placeholder="What it is, what it is good and bad at, what you learned using it…"
						class="mt-2 min-h-[92px] w-full flex-1 resize-y rounded-sm border border-stone-800 bg-black/30 px-2 py-1.5 text-[12px] leading-relaxed text-stone-300 placeholder:text-stone-700 focus:border-amber-500/60 focus:outline-none"
					></textarea>
				</div>
			</div>

			<div class="grid gap-3 p-5 sm:grid-cols-2">
				<div class="sm:col-span-2">
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Price</span>
					<div class="mt-1 flex items-center gap-2">
						<div class="flex overflow-hidden rounded-sm border border-stone-800">
							{#each ['diy', 'paid'] as kind (kind)}
								<button
									onclick={() => save(tool, { price_kind: kind as 'diy' | 'paid' })}
									class="px-2.5 py-1 text-[10px] tracking-[0.14em] uppercase transition
									{tool.price_kind === kind
										? 'bg-amber-500/15 text-amber-300'
										: 'text-stone-500 hover:text-stone-300'}"
								>
									{kind}
								</button>
							{/each}
						</div>
						<!-- Shown for both: building a thing still costs, and that is
						     worth writing down. -->
						<input
							value={tool.price}
							onchange={(e) => save(tool, { price: e.currentTarget.value })}
							placeholder={tool.price_kind === 'diy' ? 'what the parts cost' : 'what it cost'}
							class="min-w-0 flex-1 rounded-sm border border-stone-800 bg-black/40 px-2 py-1 text-[12px] text-stone-200 focus:border-amber-500/60 focus:outline-none"
						/>
					</div>
				</div>

				{#each [['type', 'Type', 'what kind of thing it is'], ['model', 'Model', 'make and model']] as [key, label, hint] (key)}
					<label class="block">
						<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">{label}</span>
						<input
							value={tool[key as 'type' | 'model']}
							onchange={(e) => save(tool, { [key]: e.currentTarget.value })}
							placeholder={hint}
							class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1 text-[12px] text-stone-200 focus:border-amber-500/60 focus:outline-none"
						/>
					</label>
				{/each}

				<label class="block">
					<span class="text-[10px] tracking-[0.16em] text-stone-500 uppercase">Day acquired</span>
					<input
						value={tool.acquired}
						onchange={(e) => save(tool, { acquired: e.currentTarget.value })}
						type="date"
						class="mt-1 w-full rounded-sm border border-stone-800 bg-black/40 px-2 py-1 text-[12px] text-stone-200 focus:border-amber-500/60 focus:outline-none"
					/>
				</label>

				<div class="flex items-center gap-2 border-t border-stone-800 pt-3 sm:col-span-2">
					{#if tool.retired}
						<!-- Un-retiring is ordinary: things come back into service. -->
						<button
							onclick={() => save(tool, { retired: '' })}
							disabled={busy}
							class="flex-1 rounded-sm border border-stone-700 py-1.5 text-[11px] tracking-[0.16em] text-stone-400 uppercase transition hover:text-stone-200"
						>
							back in service
						</button>
					{:else}
						<button
							onclick={() => save(tool, { retired: today() })}
							disabled={busy}
							class="flex-1 rounded-sm border border-stone-700 py-1.5 text-[11px] tracking-[0.16em] text-stone-400 uppercase transition hover:border-amber-500/50 hover:text-amber-300"
						>
							retire
						</button>
					{/if}
					<button
						onclick={() => drop(tool)}
						disabled={busy}
						class="rounded-sm border border-rose-900/60 px-3 py-1.5 text-[11px] tracking-[0.16em] text-rose-400/80 uppercase transition hover:bg-rose-500/10"
					>
						delete
					</button>
				</div>
			</div>
		</div>
	</div>
{/if}
