<script lang="ts">
	/**
	 * The machine behind the Portal: what is on the disk, where the copy goes,
	 * and the one button that brings a stale server back.
	 *
	 * Deliberately outside the fiction. Everything on `/` is the Portal
	 * speaking to an Instance; this is the owner looking at the hardware, and
	 * it says so plainly.
	 *
	 * "Back up now" starts `backup.sh` (or `backup.ps1`) and does not
	 * reimplement one line of it — its refusals are printed verbatim, and the
	 * commonest one, "same device", is the one that catches an unmounted disk.
	 */
	import {
		bytes,
		getBackup,
		getStorage,
		restartServer,
		runBackup,
		type BackupStatus,
		type StorageReport
	} from '$lib/api';

	let report = $state<StorageReport | null>(null);
	let backup = $state<BackupStatus | null>(null);
	let error = $state<string | null>(null);
	let busy = $state<string | null>(null);

	async function load() {
		try {
			[report, backup] = await Promise.all([getStorage(), getBackup()]);
			error = null;
		} catch (e) {
			error = (e as Error).message;
		}
	}

	$effect(() => {
		void load();
	});

	async function act(label: string, work: () => Promise<unknown>) {
		busy = label;
		error = null;
		try {
			await work();
		} catch (e) {
			error = (e as Error).message;
		}
		busy = null;
		await load();
	}

	// A backup of a media library takes minutes, so the POST starts it and this
	// watches — slowly, because the only thing that changes is a boolean.
	$effect(() => {
		if (!backup?.running) return;
		const t = setInterval(async () => {
			try {
				backup = await getBackup();
			} catch {
				/* the run outlives a hiccup in the poll */
			}
		}, 3000);
		return () => clearInterval(t);
	});

	async function restart() {
		busy = 'restart';
		try {
			await restartServer();
		} catch {
			/* it may well die mid-reply — that is the request working */
		}
		setTimeout(() => location.reload(), 4000);
	}

	const largest = $derived(Math.max(1, ...(report?.parts ?? []).map((p) => p.bytes)));

	const lastBackup = $derived.by(() => {
		if (!backup) return '';
		if (backup.running) return 'Backing up now…';
		if (!backup.last) return `Never backed up here · would copy to ${backup.destination}`;
		const days = Math.floor((backup.seconds_ago ?? 0) / 86400);
		const when = days === 0 ? 'today' : days === 1 ? 'yesterday' : `${days} days ago`;
		return `Last backup ${when} · to ${backup.destination}`;
	});
</script>

<div class="min-h-0 flex-1 overflow-y-auto">
	<div class="mx-auto flex max-w-[880px] flex-col gap-10 px-6 pt-8 pb-16 sm:px-10">
		<div class="flex flex-col gap-3">
			<span class="p-label">Settings</span>
			<h1 class="p-title">On disk</h1>
			{#if report}
				<p class="text-[12px] break-all text-neutral-600">{report.path}</p>
			{/if}
		</div>

		{#if error}
			<p class="text-[13px] text-error">{error}</p>
		{/if}

		{#if report}
			<section class="flex flex-col gap-5">
				<p class="text-[34px] leading-none font-extrabold tracking-[-0.03em] text-ink tabular-nums">
					{bytes(report.total_bytes)}
				</p>
				{#each report.parts as part (part.key)}
					<div class="flex max-w-[640px] flex-col gap-1.5">
						<div class="flex items-baseline gap-3">
							<span class="text-[14px] font-semibold text-neutral-800">{part.label}</span>
							<span class="text-[12px] text-neutral-600 tabular-nums">
								{bytes(part.bytes)} · {part.files}
								{part.files === 1 ? 'file' : 'files'}
							</span>
						</div>
						<span class="h-[5px] bg-neutral-300">
							<span
								class="block h-full bg-neutral-600"
								style="width: {Math.max(1, (part.bytes / largest) * 100)}%"
							></span>
						</span>
						<span class="text-[12px] leading-[1.6] text-neutral-600">{part.hint}</span>
					</div>
				{/each}
			</section>
		{:else}
			<p class="text-[13px] text-neutral-600">reading…</p>
		{/if}

		<section class="flex flex-col gap-3">
			<h2 class="p-label">Backup</h2>
			<button
				type="button"
				class="accent-fill h-11 self-start px-5 text-[13px] font-semibold disabled:opacity-50"
				disabled={busy !== null || backup?.running}
				onclick={() => act('backup', runBackup)}
			>
				{backup?.running ? 'Backing up…' : 'Back up now'}
			</button>
			<span class="text-[12px] text-neutral-700">{lastBackup}</span>
			{#if backup?.result && !backup.result.ok}
				<span class="text-[12px] text-error">{backup.result.message}</span>
			{/if}
		</section>

		<section class="flex flex-col gap-3">
			<h2 class="p-label">Server</h2>
			<button
				type="button"
				class="h-11 self-start px-5 text-[13px] text-neutral-800 transition-colors hover:text-ink disabled:opacity-50"
				style="box-shadow: inset 0 0 0 1px var(--color-neutral-400)"
				disabled={busy !== null}
				onclick={restart}
			>
				{busy === 'restart' ? 'Restarting…' : 'Restart server'}
			</button>
		</section>
	</div>
</div>
