<script lang="ts">
	/**
	 * Settings — disk, the folder/tag mapping, how the Log behaves, the monitor,
	 * the manual. One at a time, down a column on the left.
	 *
	 * It was one screen with everything stacked on it, and it stopped fitting.
	 * Five sections in two columns meant the only way to reach the last of them
	 * was to scroll, and **scrolling is the Log's gesture.** The Log is a feed of
	 * days and is *supposed* to run off the bottom of the screen; a settings
	 * screen that behaves the same way makes the app feel like it is all one
	 * long document. Here the page does not scroll: you pick a section and it is
	 * the whole right-hand side.
	 *
	 * The column is the album screen's sidebar in a different context, and
	 * deliberately so — same 252px, same card of rows on the tinted ground, same
	 * `accent-fill` on the one you are in. Two sidebars that behave alike are one
	 * thing to learn.
	 *
	 * **Which section is open lives in the URL** (`?s=monitor`), which is what
	 * makes the rows plain links: back and forward work, a reload puts you back
	 * where you were, and there is no third copy of "where am I" to keep in sync.
	 * The route has no `load`, so switching sections re-runs nothing — `report`,
	 * `backup` and `folders` are fetched once on mount and survive the
	 * navigation.
	 *
	 * Why these five and not some other cut:
	 *
	 *   - **Disk**, because there is exactly one copy of the photographs and the
	 *     person who owns them should be able to see how much of it there is
	 *     without opening a terminal. The parts are split by *what losing them
	 *     would cost* rather than by what they are: an index carries a
	 *     `rebuildable` chip because deleting it costs a rebuild and nothing
	 *     else, and the log does not, because it is the truth.
	 *   - **Folders & tags**, which used to be a screen of its own. What it
	 *     shows is the mapping at a glance and the one number that ever needs
	 *     acting on — how many tags point nowhere.
	 *   - **Log**, where the two model additions the redesign assumes are
	 *     switches rather than a fork in the design. Neither stores anything;
	 *     see `settings.svelte.ts`.
	 *   - **Monitor**, because the glass is the loudest opinion in the app and
	 *     the person reading through it is the only one who can say whether it
	 *     is too much. The dials write the same six custom properties the effect
	 *     already reads, so this screen adjusts the monitor without knowing
	 *     anything about how it is drawn — see `monitor.svelte.ts`.
	 *   - **Manual**, which is read closely once and skimmed rarely after that.
	 *     It is a link out rather than a pane: it is a document, and it already
	 *     has a route that can hold one.
	 *
	 * "Back up now" starts `backup.sh` and does not reimplement one line of it.
	 * The device check and the missing `--delete` are what make that script
	 * safe, and a second copy of that reasoning behind a button is a second
	 * place for it to rot.
	 */
	import { page } from '$app/state';
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

	/**
	 * The column. `hint` is the one number or word that is worth seeing without
	 * opening the section — the same job the album count does in the Log's
	 * sidebar. Silence is the default: a section with nothing to say shows
	 * nothing rather than a zero.
	 */
	type SectionId = 'disk' | 'folders' | 'log' | 'monitor';

	const SECTIONS: { id: SectionId; label: string; title: string; blurb: string }[] = [
		{
			id: 'disk',
			label: 'Disk',
			title: 'On disk',
			blurb: 'What is here, what it would cost to lose, and where the copy goes.'
		},
		{
			id: 'folders',
			label: 'Folders & tags',
			title: 'Folders & tags',
			blurb: 'Which tags land in which folder. Membership is read from your lines, never stored.'
		},
		{
			id: 'log',
			label: 'Log',
			title: 'Log',
			blurb: 'How the days are grouped on the way out. None of it changes a stored byte.'
		},
		{
			id: 'monitor',
			label: 'Monitor',
			title: 'Monitor',
			blurb: 'The glass over the app: scanlines, vignette, grain, bloom and the light on the tube.'
		}
	];

	/** An unknown or absent `?s=` is Disk rather than an error — a settings
	 *  screen is not somewhere a bad URL should be able to leave you nowhere. */
	const current = $derived(
		SECTIONS.find((s) => s.id === page.url.searchParams.get('s')) ?? SECTIONS[0]
	);

	const hint = $derived.by(() => {
		return {
			disk: report ? bytes(report.total_bytes) : '',
			folders: unmapped > 0 ? `${unmapped} loose` : '',
			log: '',
			monitor: monitor.on ? '' : 'off'
		} as Record<SectionId, string>;
	});

	const largest = $derived(Math.max(1, ...(report?.parts ?? []).map((p) => p.bytes)));

	/** `41.6` and `GB` separately, because the design sets them at 52px and
	 *  20px and a single formatted string cannot be split after the fact. */
	const total = $derived(bytes(report?.total_bytes ?? 0).split(' '));

	const lastBackup = $derived.by(() => {
		if (!backup) return '';
		if (backup.running) return 'Backing up now…';
		if (!backup.last) return `Never backed up here · would copy to ${backup.destination}`;
		const days = Math.floor((backup.seconds_ago ?? 0) / 86400);
		const when = days === 0 ? 'today' : days === 1 ? 'yesterday' : `${days} days ago`;
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
	 * halo on the type, then the light sitting on the front of the glass.
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
			key: 'sheen',
			label: 'Glass',
			hint: 'Light on the front of the tube, and how round its corners are.',
			min: 0,
			max: 2,
			step: 0.05,
			format: (v) => `${v.toFixed(2)}×`
		}
	];

	const LOG_SWITCHES = $derived([
		{
			label: 'Merge quiet stretches',
			on: logSettings.mergeQuiet,
			set: (v: boolean) => logSettings.setMergeQuiet(v),
			hint: 'Days with a line or two and no media collapse into one strip that expands.'
		},
		{
			label: 'Albums restart each year',
			on: logSettings.yearAlbums,
			set: (v: boolean) => logSettings.setYearAlbums(v),
			hint: 'A folder belongs to a year, so every timeline is capped at twelve months.'
		}
	]);
</script>

<div class="flex h-dvh flex-col">
	<!-- The pill in the same corner as on every other screen, above the column
	     rather than inside it — the same arrangement the album screen arrived at,
	     and for the same reason. -->
	<div class="flex shrink-0 items-center justify-between gap-6 px-[34px] pt-[22px] pb-[22px]">
		<TabPill />
		<!-- The data root, truncated rather than allowed to set the page's width.
		     An absolute path is as long as it is, and at phone width this one span
		     was pushing the document wide enough to raise a horizontal scrollbar —
		     which then made every screen scroll ten pixels vertically, for no
		     reason a reader could see. -->
		<span class="min-w-0 truncate font-mono text-[12px] text-neutral-700">
			{report?.path ?? ''}
		</span>
	</div>

	<div class="flex min-h-0 flex-1">
		<!-- ── The column ──────────────────────────────────────────────────
		     No border. Cards on the tinted ground, which is the rule everywhere
		     in this design: a group is a white surface, never a rule. -->
		<!-- Same 34px gutter as the album sidebar and the shelf rail: it is the
		     page's, the nav pill is at it on every screen, and this aside is what
		     sits under the pill here. -->
		<aside class="flex w-[274px] shrink-0 flex-col pb-6 pl-[34px] pr-3">
			<div class="flex items-baseline gap-[9px] pb-5">
				<span class="text-[22px] font-extrabold tracking-[-0.02em]">Settings</span>
			</div>

			<nav class="flex flex-col gap-0.5 rounded-[14px] bg-surface p-2 shadow-md">
				{#each SECTIONS as s (s.id)}
					{@const on = s.id === current.id}
					<a
						href="/settings?s={s.id}"
						aria-current={on ? 'page' : undefined}
						class="flex items-center gap-2.5 rounded-[10px] px-3 py-[9px] transition-colors {on
							? 'accent-fill'
							: 'hover:bg-neutral-200'}"
					>
						<span class="min-w-0 flex-1 truncate {on ? 'text-[15px] font-bold' : 'text-[14px]'}">
							{s.label}
						</span>
						{#if hint[s.id]}
							<span
								class="shrink-0 font-mono text-[11px] tabular-nums {on
									? 'opacity-85'
									: 'text-neutral-700'}"
							>
								{hint[s.id]}
							</span>
						{/if}
					</a>
				{/each}
			</nav>

			<!-- Below the card, not in it: it leaves this screen, and a row that
			     navigates away sitting among four that do not is the kind of
			     thing you only click wrong once but resent every time. -->
			<a
				href="/manual"
				class="mt-2.5 flex items-center gap-2.5 rounded-[12px] px-3 py-[11px] transition-colors hover:bg-neutral-200"
			>
				<span class="min-w-0 flex-1 truncate text-[14px] text-neutral-800">Manual</span>
				<span class="shrink-0 text-[13px] text-neutral-600">→</span>
			</a>
		</aside>

		<!-- ── The section ─────────────────────────────────────────────────
		     `overflow-y-auto` is a floor, not a plan. Four of the five panes fit
		     on any screen this app runs on; the folder list is the one that
		     cannot promise to, because it is as long as the user's projects. -->
		<div class="min-w-0 flex-1 overflow-y-auto px-8 pb-12">
			<!-- Wide enough for two columns of the things that come in lists. The
			     pane is about this wide at both the packaged window's default size
			     and its minimum — the column is fixed and the cap does the rest —
			     so the two-up grids below do not need a breakpoint to be safe. -->
			<div class="max-w-[680px]">
				<h1 class="text-[18px] font-bold tracking-[-0.01em]">{current.title}</h1>
				<p class="mt-[5px] text-[13px] leading-[1.5] text-neutral-700">{current.blurb}</p>

				<div class="mt-[22px] flex flex-col gap-[22px]">
					{#if current.id === 'disk'}
						<div class="flex items-baseline gap-3.5">
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

						{#if report}
							<!-- Two up. The bars are scaled against the largest part rather
							     than against their own column, so splitting the list does not
							     change what any two of them say about each other — and one
							     tall column of five was the only thing on this screen that
							     still ran off the bottom. -->
							<div class="grid grid-cols-2 gap-x-7 rounded-[16px] bg-surface px-[18px] py-1.5 shadow-md">
								{#each report.parts as part (part.key)}
									<div class="flex flex-col gap-[7px] py-[13px]">
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
											<span class="font-mono text-[13px] text-neutral-800">
												{bytes(part.bytes)}
											</span>
										</div>
										<span class="block h-[7px] overflow-hidden rounded-[4px] bg-neutral-200">
											<!-- Widths are relative to the biggest part, not the
											     total: with media at 99% every other bar would be
											     invisible, which is exactly when you most want to
											     see what the small ones are.

											     The irreplaceable parts take the accent; the derived
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

						<div class="flex flex-col gap-2.5">
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

							<span class="text-[12px] text-neutral-700">{lastBackup}</span>
							{#if backup?.result && !backup.result.ok}
								<!-- `backup.sh`'s own refusals, verbatim. They explain
								     themselves better than anything this screen could
								     invent, and the most common one — the destination is on
								     the same disk — is the one that catches an unmounted
								     backup drive. -->
								<span class="text-[12px] text-accent-700">{backup.result.message}</span>
							{/if}
						</div>
					{:else if current.id === 'folders'}
						<!-- Rows that go somewhere answer to the touch, the way the album
						     list in the Log does. They were flat links that did nothing
						     under a finger, which on a touch screen reads as a list rather
						     than as a set of doors. -->
						<div class="rounded-[16px] bg-surface px-2 py-2 shadow-md">
							{#each mapped as folder (folder.id)}
								{@const shipped = folder.state === 'shipped'}
								<a
									href="/folders/{folder.id}"
									class="flex items-center gap-3 rounded-[10px] px-2 py-3 transition-colors hover:bg-neutral-200"
								>
									<span
										class="h-2 w-2 shrink-0 rounded-full"
										style="background:{shipped
											? 'var(--color-neutral-400)'
											: phosphorize(folder.color)}"
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
					{:else if current.id === 'log'}
						<div class="rounded-[16px] bg-surface px-4 py-2 shadow-md">
							<div class="flex items-center gap-3.5 py-[13px]">
								<span class="flex-1 text-[14px]">Opens on</span>
								<Segmented
									options={OPENS_ON}
									value={logSettings.openOn}
									onpick={(v) => logSettings.setOpenOn(v)}
									label="what the Log opens on"
								/>
							</div>

							{#each LOG_SWITCHES as row (row.label)}
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
					{:else if current.id === 'monitor'}
						<div class="rounded-[16px] bg-surface px-4 py-2 shadow-md">
							<div class="flex items-center gap-3.5 py-[13px]">
								<span class="flex-1">
									<span class="block text-[14px]">Tube</span>
									<span class="mt-0.5 block text-[12px] leading-[1.45] text-neutral-700">
										Off takes the glass away entirely. Your numbers are kept.
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

							<!-- Two up, under the switch rather than beside it. Six dials
							     in one column was the other thing on this screen tall enough
							     to need scrolling, and they are independent of each other —
							     nothing is lost by reading them in pairs. -->
							<div class="grid grid-cols-2 gap-x-7">
								{#each DIALS as dial (dial.key)}
									{@const value = monitor[dial.key]}
								<!-- The whole row goes quiet with the tube, not just the
								     slider. `:disabled` on the input alone is not enough:
								     WebKitGTK — the engine `desktop.py` ships — computes the
								     opacity and then paints the restyled thumb at full
								     strength anyway, so the one control that had to look
								     unavailable was the one that still looked lit. -->
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

						<!-- Absent rather than disabled at the defaults: a control that is
						     always there and usually does nothing has to be read every
						     time to find out which. -->
						{#if !monitor.isDefault}
							<button
								type="button"
								class="lift lift-sm w-fit rounded-[11px] bg-surface px-4 py-[11px] text-[13px] font-semibold shadow-sm"
								onclick={() => monitor.reset()}
							>
								Reset to defaults
							</button>
						{/if}
					{/if}

					{#if error}
						<span class="text-[12px] text-accent-700">{error}</span>
					{/if}
				</div>
			</div>
		</div>
	</div>
</div>
