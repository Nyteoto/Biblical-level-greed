<script lang="ts">
	/**
	 * Settings — disk, the folder/tag mapping, how the Log behaves, the manual.
	 *
	 * This screen absorbed what the tech tree's tabs used to hold. Four things
	 * live here now and they are here for one reason each:
	 *
	 *   - **On disk**, because there is exactly one copy of the photographs and
	 *     the person who owns them should be able to see how much of it there
	 *     is without opening a terminal. The parts are split by *what losing
	 *     them would cost* rather than by what they are: an index carries a
	 *     `rebuildable` chip because deleting it costs a rebuild and nothing
	 *     else, and the log does not, because it is the truth.
	 *   - **Folders & tags**, which used to be a screen of its own. What it
	 *     actually shows here is the mapping at a glance and the one number
	 *     that ever needs acting on — how many tags point nowhere.
	 *   - **Log**, where the two model additions the redesign assumes are
	 *     switches rather than a fork in the design. Neither stores anything;
	 *     see `settings.svelte.ts`.
	 *   - **Monitor**, because the glass is the loudest opinion in the app and
	 *     the person reading through it is the only one who can say whether it
	 *     is too much. The dials write the same five custom properties and the
	 *     same corner displacement the effect already reads, so this screen
	 *     adjusts the monitor without knowing anything about how it is drawn —
	 *     see `monitor.svelte.ts`.
	 *   - **Manual**, which is read closely once and skimmed rarely after that,
	 *     and does not earn a permanent tab.
	 *
	 * "Back up now" starts `backup.sh` and does not reimplement one line of it.
	 * The device check and the missing `--delete` are what make that script
	 * safe, and a second copy of that reasoning behind a button is a second
	 * place for it to rot.
	 */
	import Segmented from '$lib/trophic/Segmented.svelte';
	import TabPill from '$lib/trophic/TabPill.svelte';
	import { logSettings, dayBoundary, type OpenOn } from '$lib/trophic/settings.svelte';
	import { monitor, type MonitorKey } from '$lib/trophic/monitor.svelte';
	import {
		bytes,
		getBackup,
		getStorage,
		reloadFromDisk,
		runBackup,
		type BackupStatus,
		type StorageReport
	} from '$lib/api';
	import { phosphorize } from '$lib/trophic/colors';
	import { getFolders, getUnassignedTags, reindex, type Folder } from '$lib/trophic/api';

	let report = $state<StorageReport | null>(null);
	let backup = $state<BackupStatus | null>(null);
	let folders = $state<Folder[]>([]);
	let unmapped = $state(0);
	let error = $state<string | null>(null);
	let busy = $state<string | null>(null);

	$effect(() => {
		logSettings.hydrate();
		load();
	});

	async function load() {
		try {
			const [s, b, f, u] = await Promise.all([
				getStorage(),
				getBackup(),
				getFolders(),
				getUnassignedTags()
			]);
			report = s;
			backup = b;
			folders = f.folders;
			unmapped = u.total;
			error = null;
		} catch (e) {
			error = (e as Error).message;
		}
	}

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
	// watches. The interval is deliberately slow: the only thing that changes
	// is a boolean, and a spinner that polls twice a second is a spinner that
	// is doing something other than informing.
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

	// Widths are relative to the biggest part, not the total: with media at 99%
	// every other bar would be invisible, which is exactly when you most want
	// to see what the small ones are.
	const largest = $derived(Math.max(1, ...(report?.parts ?? []).map((p) => p.bytes)));

	/** `41.6` and `GB` separately, because the design sets them at 52px and
	 *  20px and a single formatted string cannot be split after the fact. */
	const total = $derived(bytes(report?.total_bytes ?? 0).split(' '));

	const lastBackup = $derived.by(() => {
		if (!backup) return '';
		if (backup.running) return 'Backing up now…';
		if (!backup.last) return `Never backed up here · would copy to ${backup.destination}`;
		const days = Math.floor((backup.seconds_ago ?? 0) / 86400);
		const when =
			days === 0 ? 'today' : days === 1 ? 'yesterday' : `${days} days ago`;
		return `Last backup ${when} · ${bytes(report?.total_bytes ?? 0)} to ${backup.destination}`;
	});

	/** Which tags point at a folder, in that folder's own colour. The mapping
	 *  is the definition of the folder, not a summary of it. */
	const mapped = $derived(folders.filter((f) => f.tags.length > 0 || f.state === 'active'));

	const OPENS_ON: { value: OpenOn; label: string }[] = [
		{ value: 'shelf', label: 'Year shelf' },
		{ value: 'latest', label: 'Latest day' }
	];

	/**
	 * The six dials, in the order the eye meets the effect: the lines across
	 * the picture, then the darkening at its edges, then the noise, then the
	 * halo on the type, then the bend of the tube.
	 *
	 * Each range starts at zero — every part of the monitor can be taken away
	 * on its own, which is the only way to find out which part you actually
	 * object to. The tops are where the effect stops reading as a monitor and
	 * starts reading as damage; they are generous, not safe.
	 */
	const DIALS: {
		key: MonitorKey;
		label: string;
		hint: string;
		min: number;
		max: number;
		step: number;
		format: (value: number) => string;
	}[] = [
		{
			key: 'scanAlpha',
			label: 'Scanlines',
			hint: 'How dark the lines between the lines are.',
			min: 0,
			max: 0.2,
			step: 0.005,
			format: (v) => v.toFixed(3)
		},
		{
			key: 'scanPeriod',
			label: 'Line spacing',
			hint: 'How far apart they sit. Tighter is a smaller tube.',
			min: 2,
			max: 8,
			step: 0.5,
			format: (v) => `${v}px`
		},
		{
			key: 'vignette',
			label: 'Vignette',
			hint: 'The falloff into the corners.',
			min: 0,
			max: 0.75,
			step: 0.01,
			format: (v) => v.toFixed(2)
		},
		{
			key: 'grain',
			label: 'Grain',
			hint: 'Sensor noise over the whole picture.',
			min: 0,
			max: 0.08,
			step: 0.002,
			format: (v) => v.toFixed(3)
		},
		{
			key: 'bloom',
			label: 'Bloom',
			hint: 'The halo lit type throws. At zero the text is flat.',
			min: 0,
			max: 2,
			step: 0.05,
			format: (v) => `${v.toFixed(2)}×`
		},
		{
			key: 'curve',
			label: 'Curve',
			hint: 'How far the corners of the picture move. Layout does not follow.',
			min: 0,
			max: 28,
			step: 1,
			format: (v) => `${v}px`
		}
	];
</script>

<div class="flex h-dvh flex-col">
	<div class="flex shrink-0 items-center justify-between px-[34px] pt-[22px]">
		<TabPill />
		<span class="font-mono text-[12px] text-neutral-700">{report?.path ?? ''}</span>
	</div>

	<div class="flex min-h-0 flex-1 gap-[26px] overflow-y-auto px-[34px] pt-[26px] pb-10">
		<!-- ── Disk ────────────────────────────────────────────────────────── -->
		<div class="flex min-w-0 flex-[1.25] flex-col gap-[22px]">
			<div>
				<div class="text-[10px] font-bold tracking-[0.22em] text-accent-700 uppercase">
					On disk
				</div>
				<div class="mt-2 flex items-baseline gap-3.5">
					<span class="text-[52px] leading-[0.95] font-extrabold tracking-[-0.035em]">
						{total[0]}
					</span>
					<span class="text-[20px] font-bold text-neutral-700">{total[1] ?? ''}</span>
					{#if report}
						<span class="text-[13px] text-neutral-700 tabular-nums">
							{report.total_files.toLocaleString()} files · one copy, on this machine
						</span>
					{/if}
				</div>
			</div>

			{#if report}
				<div class="rounded-[16px] bg-surface px-[18px] py-1.5 shadow-md">
					{#each report.parts as part (part.key)}
						<div class="flex flex-col gap-[9px] py-[15px]">
							<div class="flex items-baseline gap-3">
								<span class="text-[15px] font-bold">{part.label}</span>
								{#if part.recoverable}
									<span
										class="rounded-md bg-neutral-200 px-[7px] py-[3px] text-[9px] font-bold tracking-[0.12em] text-neutral-700 uppercase"
										title="Derived data — deleting it only costs a rebuild"
									>
										rebuildable
									</span>
								{/if}
								<span class="flex-1"></span>
								<span class="font-mono text-[13px] text-neutral-800">{bytes(part.bytes)}</span>
							</div>
							<span class="block h-[7px] overflow-hidden rounded-[4px] bg-neutral-200">
								<!-- The irreplaceable parts take the accent; the derived
								     ones take a grey. The bar's colour is the same
								     statement as the chip beside the label. -->
								<span
									class="block h-full rounded-[4px]"
									style="width:{part.bytes === 0
										? 0
										: Math.max(1.5, (part.bytes / largest) * 100)}%;
									       background:{part.recoverable
										? 'var(--color-neutral-500)'
										: 'linear-gradient(90deg,var(--color-accent-500),var(--color-accent-700))'}"
								></span>
							</span>
							<span class="text-[12px] text-neutral-700">
								{part.files.toLocaleString()}
								{part.files === 1 ? 'file' : 'files'} · {part.hint}
							</span>
						</div>
					{/each}
				</div>
			{:else}
				<p class="text-[13px] text-neutral-700">reading…</p>
			{/if}

			<div class="flex flex-wrap gap-2.5">
				<button
					type="button"
					class="lift lift-sm rounded-[11px] bg-surface px-4 py-[11px] text-[13px] font-semibold shadow-sm disabled:opacity-50"
					disabled={busy !== null}
					onclick={() => act('reindex', reindex)}
				>
					{busy === 'reindex' ? 'rebuilding…' : 'Rebuild index'}
				</button>
				<button
					type="button"
					class="lift lift-sm rounded-[11px] bg-surface px-4 py-[11px] text-[13px] font-semibold shadow-sm disabled:opacity-50"
					disabled={busy !== null}
					onclick={() => act('reload', reloadFromDisk)}
				>
					{busy === 'reload' ? 'reading…' : 'Reload from disk'}
				</button>
				<button
					type="button"
					class="accent-fill rounded-[11px] px-4 py-[11px] text-[13px] font-semibold disabled:opacity-50"
					disabled={busy !== null || backup?.running}
					onclick={() => act('backup', runBackup)}
				>
					{backup?.running ? 'Backing up…' : 'Back up now'}
				</button>
			</div>

			<span class="-mt-2 text-[12px] text-neutral-700">{lastBackup}</span>
			{#if backup?.result && !backup.result.ok}
				<!-- `backup.sh`'s own refusals, verbatim. They explain themselves
				     better than anything this screen could invent, and the most
				     common one — the destination is on the same disk — is the one
				     that catches an unmounted backup drive. -->
				<span class="text-[12px] text-accent-700">{backup.result.message}</span>
			{/if}

			{#if error}
				<span class="text-[12px] text-accent-700">{error}</span>
			{/if}
		</div>

		<!-- ── Folders, the Log's behaviour, the Manual ─────────────────────── -->
		<div class="flex min-w-0 flex-1 flex-col gap-[22px]">
			<div>
				<div class="text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">
					Folders &amp; tags
				</div>
				<!-- Rows that go somewhere answer to the touch, the way the album
				     list in the Log does. They were flat links that did nothing
				     under a finger, which on a touch screen reads as a list rather
				     than as a set of doors. -->
				<div class="mt-2.5 rounded-[16px] bg-surface px-2 py-2 shadow-md">
					{#each mapped as folder (folder.id)}
						{@const shipped = folder.state === 'shipped'}
						<a
							href="/folders/{folder.id}"
							class="flex items-center gap-3 rounded-[10px] px-2 py-3 transition-colors hover:bg-neutral-200"
						>
							<span
								class="h-2 w-2 shrink-0 rounded-full"
								style="background:{shipped ? 'var(--color-neutral-400)' : phosphorize(folder.color)}"
							></span>
							<span
								class="min-w-0 flex-1 truncate text-[14px] {shipped
									? 'text-neutral-800'
									: 'font-semibold'}"
							>
								{folder.name}
							</span>
							{#if shipped}
								<span
									class="shrink-0 text-[10px] font-bold tracking-[0.1em] text-neutral-700 uppercase"
								>
									shipped
								</span>
							{:else}
								<span
									class="shrink-0 truncate font-mono text-[12px]"
									style="color:{phosphorize(folder.color)}"
								>
									{folder.tags.map((t) => `<${t}>`).join(' ')}
								</span>
							{/if}
						</a>
					{:else}
						<p class="px-2 py-3 text-[13px] text-neutral-700">
							no folders yet — a folder is where a tag lands.
						</p>
					{/each}

					<a
						href="/mapping"
						class="flex items-center gap-3 rounded-[10px] px-2 py-3 transition-colors hover:bg-neutral-200"
					>
						<span class="min-w-0 flex-1 text-[14px] font-semibold text-accent-700">
							{unmapped}
							{unmapped === 1 ? 'tag points' : 'tags point'} nowhere
						</span>
						<span class="shrink-0 text-[13px] font-semibold">Map them →</span>
					</a>
				</div>
			</div>

			<div>
				<div class="text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">Log</div>
				<div class="mt-2.5 rounded-[16px] bg-surface px-4 py-2 shadow-md">
					<div class="flex items-center gap-3.5 py-[13px]">
						<span class="flex-1 text-[14px]">Opens on</span>
						<Segmented
							options={OPENS_ON}
							value={logSettings.openOn}
							onpick={(v) => logSettings.setOpenOn(v)}
							label="what the Log opens on"
						/>
					</div>

					{#each [{ label: 'Merge quiet stretches', on: logSettings.mergeQuiet, set: (v: boolean) => logSettings.setMergeQuiet(v), hint: 'Days with a line or two and no media collapse into one strip that expands.' }, { label: 'Albums restart each year', on: logSettings.yearAlbums, set: (v: boolean) => logSettings.setYearAlbums(v), hint: 'A folder belongs to a year, so every timeline is capped at twelve months.' }] as row (row.label)}
						<div class="flex items-center gap-3.5 py-[13px]">
							<span class="flex-1">
								<span class="block text-[14px]">{row.label}</span>
								<span class="mt-0.5 block text-[12px] leading-[1.45] text-neutral-700">
									{row.hint}
								</span>
							</span>
							<button
								type="button"
								role="switch"
								aria-checked={row.on}
								aria-label={row.label}
								class="flex h-[26px] w-[44px] shrink-0 items-center rounded-full p-[3px] transition-colors {row.on
									? 'accent-fill-flat justify-end'
									: 'justify-start bg-neutral-300'}"
								onclick={() => row.set(!row.on)}
							>
								<span class="h-5 w-5 rounded-full bg-surface shadow-sm"></span>
							</button>
						</div>
					{/each}

					<div class="flex items-center gap-3.5 py-[13px]">
						<span class="flex-1 text-[14px]">Day starts at</span>
						<!-- Read from the browser rather than configured. The backend
						     files every event under the user's local day, and a
						     control here would only be a way to make the two
						     disagree. -->
						<span class="font-mono text-[13px] text-neutral-800">{dayBoundary()}</span>
					</div>
				</div>
			</div>

			<div>
				<div class="flex items-baseline gap-3">
					<div class="text-[10px] font-bold tracking-[0.22em] text-neutral-600 uppercase">
						Monitor
					</div>
					<span class="flex-1"></span>
					<!-- Absent rather than disabled at the defaults: a control that
					     is always there and usually does nothing has to be read
					     every time to find out which. -->
					{#if !monitor.isDefault}
						<button
							type="button"
							class="text-[12px] font-semibold text-neutral-700 hover:text-ink"
							onclick={() => monitor.reset()}
						>
							Reset
						</button>
					{/if}
				</div>

				<div class="mt-2.5 rounded-[16px] bg-surface px-4 py-2 shadow-md">
					<div class="flex items-center gap-3.5 py-[13px]">
						<span class="flex-1">
							<span class="block text-[14px]">Glass</span>
							<span class="mt-0.5 block text-[12px] leading-[1.45] text-neutral-700">
								Scanlines, vignette, grain, bloom and the curve of the tube.
							</span>
						</span>
						<button
							type="button"
							role="switch"
							aria-checked={monitor.on}
							aria-label="the monitor effect"
							class="flex h-[26px] w-[44px] shrink-0 items-center rounded-full p-[3px] transition-colors {monitor.on
								? 'accent-fill-flat justify-end'
								: 'justify-start bg-neutral-300'}"
							onclick={() => monitor.setOn(!monitor.on)}
						>
							<span class="h-5 w-5 rounded-full bg-surface shadow-sm"></span>
						</button>
					</div>

					{#each DIALS as dial (dial.key)}
						{@const value = monitor[dial.key]}
						<!-- The whole row goes quiet with the tube, not just the slider.
						     `:disabled` on the input alone is not enough: WebKitGTK —
						     the engine `desktop.py` ships — computes the opacity and
						     then paints the restyled thumb at full strength anyway,
						     so the one control that had to look unavailable was the
						     one that still looked lit. -->
						<div
							class="flex flex-col gap-[3px] py-[11px] transition-opacity {monitor.on
								? ''
								: 'opacity-40'}"
						>
							<div class="flex items-baseline gap-3">
								<span class="text-[14px]">{dial.label}</span>
								<span class="flex-1"></span>
								<span class="font-mono text-[12px] text-neutral-800 tabular-nums">
									{dial.format(value)}
								</span>
							</div>
							<!-- The whole point of putting these here is that the
							     screen you are adjusting is the screen you are
							     looking at, so they write on every input event
							     rather than on release. -->
							<input
								type="range"
								class="dial"
								min={dial.min}
								max={dial.max}
								step={dial.step}
								{value}
								disabled={!monitor.on}
								aria-label={dial.label}
								style="--dial-fill:{((value - dial.min) / (dial.max - dial.min)) * 100}%"
								oninput={(e) => monitor.set(dial.key, Number(e.currentTarget.value))}
							/>
							<span class="text-[12px] leading-[1.45] text-neutral-700">{dial.hint}</span>
						</div>
					{/each}
				</div>
			</div>

			<a
				href="/manual"
				class="lift lift-md flex items-center gap-3.5 rounded-[16px] bg-surface px-[18px] py-4 shadow-md"
			>
				<div class="min-w-0 flex-1">
					<div class="text-[15px] font-bold">Manual</div>
					<div class="mt-[3px] text-[12px] leading-[1.45] text-neutral-700">
						What the syntax does, and why the log is append-only.
					</div>
				</div>
				<span class="text-[18px] text-neutral-600">→</span>
			</a>
		</div>
	</div>
</div>
