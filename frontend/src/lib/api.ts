/** One evaluated gate on starting a node. */
export interface NodeCondition {
	key: string;
	met: boolean;
	label: string;
	detail: string;
	/** XP it costs to clear. 0 when the condition is not bought, but met. */
	cost: number;
}

export type NodeStatus =
	| 'locked' // a hard prerequisite is unmet — you cannot usefully start
	| 'open' // only soft prerequisites are unmet — start anyway if you like
	| 'available'
	| 'active'
	| 'done'
	| 'maintenance' // a completed drill that has gone stale
	| 'sealed' // prerequisites met, the XP price is not paid
	| 'standing'; // a reminder: nothing to start, nothing to finish

/** Decides how a node accrues, whether it completes, and how it renders. */
export type NodeKind = 'drill' | 'study' | 'project' | 'exam' | 'social' | 'reminder';

/** Decides how many nodes are active at once. */
export type DomainShape = 'ladder' | 'strands' | 'cycles';

export interface Reading {
	day: string;
	value: number;
}

/** Estimate vs what it actually took. `settled` means the gate was called,
 * so `actual` is final rather than still running. */
export interface Calibration {
	estimate: number;
	actual: number;
	delta: number;
	ratio: number | null;
	settled: boolean;
	over: boolean;
}

/** A domain's estimating bias across settled nodes. Ratio of totals, so big
 * nodes weigh more than small ones. */
export interface DomainCalibration {
	settled_nodes: number;
	estimate: number;
	actual: number;
	ratio: number | null;
}

export interface TreeNode {
	id: string;
	title: string;
	tier: number;
	order: number;
	kind: NodeKind;
	strand: string;
	requires: string[];
	prefers: string[];
	/** The guess: how many days you think this takes. Not a target. */
	estimate: number;
	sessions_done: number;
	/** How the guess is turning out. Empty for projects. */
	calibration: Calibration;
	/** False for projects: they accrue phases, not days. */
	counts_sessions: boolean;
	/** Phases for a project, session-days for everything else. */
	progress_done: number;
	progress_target: number;
	phases: string[];
	phases_done: string[];
	scheduled: string;
	days_until: number | null;
	decay_days: number;
	metric: string;
	metric_target: number;
	readings: Reading[];
	min_each: string;
	gate: string;
	/** How to start: books, courses, search terms. `gate` says where it ends. */
	entry: string[];
	note: string;
	status: NodeStatus;
	/** What starting this node costs. 0 for tier I, which is free everywhere. */
	unlock_price: number;
	unlocked: boolean;
	unlock_paid: number;
	/** Every gate on starting this node, already evaluated. Rendered as-is, so
	 * a new kind of condition appears in the UI without this file changing. */
	conditions: NodeCondition[];
	blocked_by: string[];
	waiting_on: string[];
	checked_today: boolean;
	ready_to_complete: boolean;
	last_session_day: string | null;
}

/** Acquiring, holding, or parked. The scheduling primitive. */
export type SeasonState = 'high' | 'low' | 'off';

export interface SeasonView {
	state: SeasonState;
	/** Width: which strands acquire in a high season. Empty means all. */
	strands: string[];
	until: string;
	ends_on: string;
	days_left: number | null;
	shipped: boolean;
	expired: boolean;
	/** Ended, by either route. Reported only — never applied for you. */
	over: boolean;
	reason: string;
	/** False when the domain has decaying nodes, which may not be parked. */
	can_park: boolean;
	decaying_count: number;
}

export interface DomainView {
	season: SeasonView;
	id: string;
	title: string;
	priority: number;
	color: string;
	cadence: string;
	cadence_label: string;
	cadence_n: number;
	source: string;
	/** Compiled into the app: not editable, not deletable, nothing priced. */
	foundation: boolean;
	shape: DomainShape;
	strands: string[];
	nodes: TreeNode[];
	tiers: number[];
	active_node_ids: string[];
	active_nodes: TreeNode[];
	active_node_id: string | null;
	active_node: TreeNode | null;
	due_today: boolean;
	checked_today: boolean;
	last_session_day: string | null;
	total_nodes: number;
	done_nodes: number;
	calibration: DomainCalibration;
	complete: boolean;
	version: number;
}

/** A plain checklist item. Not a node: no tier, no gate, no accrual. */
export interface Todo {
	id: string;
	text: string;
	/** The day it was added. The list never resets, so items can be old. */
	added: string;
}

/** The arithmetic behind today's XP, spelled out so the number stays
 * predictable rather than becoming a black box. */
export interface XpBreakdown {
	sessions: number;
	/** Of those, how many were maintenance rather than acquisition. */
	upkeep_sessions: number;
	todos: number;
	session_xp: number;
	todo_xp: number;
	streak_mult: number;
	focus_mult: number;
	acquiring_domains: string[];
	/** True while you are acquiring in `focus_domains` or fewer. */
	focused: boolean;
}

/** Derived fresh from the log every request; stored nowhere, and it never
 * influences what the board shows. */
export interface Unlock {
	day: string;
	domain: string;
	node: string;
	paid: number;
}

export interface Xp {
	/** Lifetime. Drives the level and never goes down. */
	total: number;
	/** Everything spent on unlocks, at the price paid on the day. */
	spent: number;
	/** total - spent. The currency. */
	bank: number;
	unlocks: Unlock[];
	upkeep_total: number;
	level: number;
	into_level: number;
	level_span: number;
	/** White: what yesterday left you with, inside the current level. */
	carried_pct: number;
	/** Yellow: what today has added on top. */
	today_pct: number;
	earned_today: number;
	streak: number;
	today_breakdown: XpBreakdown;
	tunables: Record<string, number>;
}

export interface Dashboard {
	today: string;
	next_rollover: string;
	domains: DomainView[];
	errors: string[];
	due_count: number;
	done_count: number;
	todos: Todo[];
	xp: Xp;
	version: number;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(`/api${path}`, {
		headers: { 'content-type': 'application/json' },
		...init
	});
	if (!res.ok) {
		const detail = await res.text();
		throw new Error(`${res.status} ${path}: ${detail}`);
	}
	return res.json() as Promise<T>;
}

export const getDashboard = () => call<Dashboard>('/dashboard');

/** One slice of what the app is using on disk. */
export interface StoragePart {
	key: string;
	label: string;
	hint: string;
	bytes: number;
	files: number;
	/** Derived data — deleting it costs nothing but a rebuild. */
	recoverable: boolean;
}

export interface StorageReport {
	path: string;
	total_bytes: number;
	total_files: number;
	parts: StoragePart[];
}

export const getStorage = () => call<StorageReport>('/storage');

/** Bytes as something a human reads at a glance. */
export function bytes(n: number): string {
	if (n < 1024) return `${n} B`;
	const units = ['KB', 'MB', 'GB', 'TB'];
	let value = n / 1024;
	let unit = 0;
	while (value >= 1024 && unit < units.length - 1) {
		value /= 1024;
		unit += 1;
	}
	return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[unit]}`;
}

export const getDomain = (id: string) => call<DomainView>(`/domains/${id}`);

export const toggleSession = (domain: string, node: string, on?: boolean, value?: number) =>
	call<{ changed: boolean; node: TreeNode }>(`/domains/${domain}/nodes/${node}/session`, {
		method: 'POST',
		body: JSON.stringify({ on: on ?? null, value: value ?? null })
	});

/** Tick one phase of a project. Projects accrue phases, not days. */
export const togglePhase = (domain: string, node: string, phase: string, on?: boolean) =>
	call<{ changed: boolean; node: TreeNode }>(`/domains/${domain}/nodes/${node}/phase`, {
		method: 'POST',
		body: JSON.stringify({ phase, on: on ?? null })
	});

export const toggleComplete = (domain: string, node: string, on?: boolean) =>
	call<{ changed: boolean; domain?: DomainView; node?: TreeNode }>(
		`/domains/${domain}/nodes/${node}/complete`,
		{ method: 'POST', body: JSON.stringify({ on: on ?? null }) }
	);

export const addTodo = (text: string) =>
	call<{ todos: Todo[] }>('/todos', { method: 'POST', body: JSON.stringify({ text }) });

/** Ticking removes the item from the list. On disk it appends a `done` op —
 * the checklist forgets it, the log does not. */
export const completeTodo = (id: string) =>
	call<{ todos: Todo[] }>(`/todos/${id}`, { method: 'DELETE' });

// -- notes: titled markdown documents, one folder per domain ----------------
// Node notes and the journal merged into this. What you write while working is
// knowledge and record at once; being made to choose which was friction.

export interface NoteSummary {
	slug: string;
	/** The document's own `# heading` when it has one, else its filename. */
	title: string;
	bytes: number;
	updated: number;
	preview: string;
}

export const listNotes = (domain: string) =>
	call<{ notes: NoteSummary[] }>(`/domains/${domain}/notes`);

export const createNote = (domain: string, title: string) =>
	call<{ slug: string; notes: NoteSummary[] }>(`/domains/${domain}/notes`, {
		method: 'POST',
		body: JSON.stringify({ title })
	});

export const getNote = (domain: string, slug: string) =>
	call<{ slug: string; text: string }>(`/domains/${domain}/notes/${slug}`);

export const saveNote = (domain: string, slug: string, text: string) =>
	call<{ ok: boolean; text: string }>(`/domains/${domain}/notes/${slug}`, {
		method: 'PUT',
		body: JSON.stringify({ text })
	});

export const deleteNote = (domain: string, slug: string) =>
	call<{ notes: NoteSummary[] }>(`/domains/${domain}/notes/${slug}`, { method: 'DELETE' });

// -- tools: the instruments a domain is practised with ----------------------
// Retirement is a date, never a delete: what a domain used to be practised on
// is the interesting half of the shelf.

export interface Tool {
	id: string;
	name: string;
	/** What it is, in your own words. Sits beside the photo. */
	description: string;
	/** Path under /media, from the upload endpoint. */
	image: string;
	price_kind: 'diy' | 'paid';
	price: string;
	acquired: string;
	retired: string;
	type: string;
	model: string;
}

export type ToolFields = Omit<Tool, 'id'>;

export const listTools = (domain: string) => call<{ tools: Tool[] }>(`/domains/${domain}/tools`);

export const addTool = (domain: string, fields: Partial<ToolFields>) =>
	call<{ tools: Tool[] }>(`/domains/${domain}/tools`, {
		method: 'POST',
		body: JSON.stringify(fields)
	});

export const patchTool = (domain: string, id: string, fields: Partial<ToolFields>) =>
	call<{ tools: Tool[] }>(`/domains/${domain}/tools/${id}`, {
		method: 'PATCH',
		body: JSON.stringify(fields)
	});

export const deleteTool = (domain: string, id: string) =>
	call<{ tools: Tool[] }>(`/domains/${domain}/tools/${id}`, { method: 'DELETE' });

export interface MediaUpload {
	ok: boolean;
	url: string;
	path: string;
	attached_to_note: boolean;
}

/** Send one image and attach it to a node's note. Raw body and no content-type
 * of ours: the server sniffs the bytes, and `call` would force JSON on it. */
export async function uploadMedia(
	file: Blob,
	domain = '',
	node = '',
	caption = ''
): Promise<MediaUpload> {
	const query = new URLSearchParams();
	// Omitted when the editor is open: it inserts the image itself, and having
	// the server append it too would put the photo in the note twice.
	if (domain && node) query.set('domain', domain), query.set('node', node);
	if (caption) query.set('caption', caption);
	const res = await fetch(`/api/media?${query}`, { method: 'POST', body: file });
	if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
	return res.json() as Promise<MediaUpload>;
}

/** Buy a node out of `sealed`. Permanent — there is no relock. */
export const unlockNode = (domain: string, node: string) =>
	call<{ node: TreeNode; xp: Xp }>(`/domains/${domain}/nodes/${node}/unlock`, {
		method: 'POST'
	});

// -- structural edits: these rewrite the domain's .toml file -----------------

export interface DomainFields {
	title?: string;
	priority?: number;
	cadence?: string;
	cadence_n?: number;
	color?: string;
	shape?: DomainShape;
	strands?: string[];
}

export interface NodeFields {
	title?: string;
	tier?: number;
	requires?: string[];
	prefers?: string[];
	estimate?: number;
	min_each?: string;
	gate?: string;
	entry?: string[];
	note?: string;
	kind?: NodeKind;
	strand?: string;
	phases?: string[];
	scheduled?: string;
	decay_days?: number;
	metric?: string;
	metric_target?: number;
}

export const createDomain = (fields: DomainFields & { title: string }) =>
	call<DomainView>('/domains', { method: 'POST', body: JSON.stringify(fields) });

export const patchDomain = (id: string, fields: DomainFields) =>
	call<DomainView>(`/domains/${id}`, { method: 'PATCH', body: JSON.stringify(fields) });

export interface SeasonFields {
	state?: SeasonState;
	strands?: string[];
	until?: string;
	ends_on?: string;
}

export const setSeason = (id: string, fields: SeasonFields) =>
	call<DomainView>(`/domains/${id}/season`, {
		method: 'POST',
		body: JSON.stringify(fields)
	});

export const deleteDomain = (id: string) =>
	call<{ deleted: string }>(`/domains/${id}`, { method: 'DELETE' });

export const createNode = (domain: string, fields: NodeFields & { title: string }) =>
	call<{ created: string; domain: DomainView }>(`/domains/${domain}/nodes`, {
		method: 'POST',
		body: JSON.stringify(fields)
	});

export const patchNode = (domain: string, node: string, fields: NodeFields) =>
	call<DomainView>(`/domains/${domain}/nodes/${node}`, {
		method: 'PATCH',
		body: JSON.stringify(fields)
	});

export const deleteNode = (domain: string, node: string) =>
	call<DomainView>(`/domains/${domain}/nodes/${node}`, { method: 'DELETE' });

export const connectNodes = (domain: string, source: string, target: string, soft = false) =>
	call<DomainView>(`/domains/${domain}/edges`, {
		method: 'POST',
		body: JSON.stringify({ source, target, soft })
	});

export const disconnectNodes = (domain: string, source: string, target: string) =>
	call<DomainView>(
		`/domains/${domain}/edges?source=${encodeURIComponent(source)}&target=${encodeURIComponent(target)}`,
		{ method: 'DELETE' }
	);

export const reorderNode = (domain: string, node: string, direction: -1 | 1) =>
	call<DomainView>(`/domains/${domain}/nodes/${node}/reorder`, {
		method: 'POST',
		body: JSON.stringify({ direction })
	});

const ROMAN: [number, string][] = [
	[40, 'XL'],
	[10, 'X'],
	[9, 'IX'],
	[5, 'V'],
	[4, 'IV'],
	[1, 'I']
];

/** Tier headers are Roman numerals, as in the reference. */
export function roman(value: number): string {
	// Tier 0 is the substrate. There is no roman numeral for it, and calling it
	// "—" would read as missing rather than as foundational.
	if (value === 0) return '0';
	let left = value;
	let out = '';
	for (const [size, glyph] of ROMAN) {
		while (left >= size) {
			out += glyph;
			left -= size;
		}
	}
	return out || '—';
}

/** Per-domain accent, resolved to literal classes so Tailwind can see them.
 *
 * `buy` is the price pill's affordable state. It is spelled out rather than
 * composed from the fields above, because Tailwind scans this file as text: a
 * class built at runtime as `hover:${a.bg}` resolves correctly in the browser
 * and is never generated into the stylesheet.
 */
export const accents: Record<
	string,
	{ text: string; border: string; bg: string; glow: string; buy: string }
> = {
	amber: {
		text: 'text-amber-300',
		border: 'border-amber-400/70',
		bg: 'bg-amber-400',
		buy: 'border-amber-400/70 text-amber-300 hover:bg-amber-400 hover:text-[#14100c] hover:border-amber-300',
		glow: 'shadow-[0_0_24px_-4px_rgba(251,191,36,0.55)]'
	},
	sky: {
		text: 'text-sky-300',
		border: 'border-sky-400/70',
		bg: 'bg-sky-400',
		buy: 'border-sky-400/70 text-sky-300 hover:bg-sky-400 hover:text-[#14100c] hover:border-sky-300',
		glow: 'shadow-[0_0_24px_-4px_rgba(56,189,248,0.55)]'
	},
	emerald: {
		text: 'text-emerald-300',
		border: 'border-emerald-400/70',
		bg: 'bg-emerald-400',
		buy: 'border-emerald-400/70 text-emerald-300 hover:bg-emerald-400 hover:text-[#14100c] hover:border-emerald-300',
		glow: 'shadow-[0_0_24px_-4px_rgba(52,211,153,0.55)]'
	},
	rose: {
		text: 'text-rose-300',
		border: 'border-rose-400/70',
		bg: 'bg-rose-400',
		buy: 'border-rose-400/70 text-rose-300 hover:bg-rose-400 hover:text-[#14100c] hover:border-rose-300',
		glow: 'shadow-[0_0_24px_-4px_rgba(251,113,133,0.55)]'
	},
	violet: {
		text: 'text-violet-300',
		border: 'border-violet-400/70',
		bg: 'bg-violet-400',
		buy: 'border-violet-400/70 text-violet-300 hover:bg-violet-400 hover:text-[#14100c] hover:border-violet-300',
		glow: 'shadow-[0_0_24px_-4px_rgba(167,139,250,0.55)]'
	},
	slate: {
		text: 'text-slate-300',
		border: 'border-slate-400/70',
		bg: 'bg-slate-400',
		buy: 'border-slate-400/70 text-slate-300 hover:bg-slate-400 hover:text-[#14100c] hover:border-slate-300',
		glow: 'shadow-[0_0_24px_-4px_rgba(148,163,184,0.55)]'
	}
};

export const accent = (color: string) => accents[color] ?? accents.slate;

/** How a domain's name is set. The foundation is the only serif in the app.
 *
 * Every other tree is a skill you chose. That one is the body doing the
 * choosing, and it should not look like a sibling of "Drumming" — the typeface
 * is the cheapest way to say so without a label explaining it. */
export const domainFace = (foundation: boolean) =>
	foundation ? 'font-serif tracking-[0.14em] italic' : '';

/** What each node kind is called, and what its progress unit is.
 *
 * These strings are the visible half of the taxonomy: a project says "phases"
 * because it accrues phases, and an exam says "prep" because its sessions are
 * preparation for something scored by somebody else.
 */
export const kinds: Record<NodeKind, { label: string; unit: string; hint: string }> = {
	drill: { label: 'drill', unit: 'sessions', hint: 'Repetition. Decays without upkeep.' },
	study: { label: 'study', unit: 'units', hint: 'Comprehension. Holds once held.' },
	project: { label: 'project', unit: 'phases', hint: 'One indivisible burst of work.' },
	exam: { label: 'exam', unit: 'prep', hint: 'Scored by someone else, on their date.' },
	social: { label: 'social', unit: 'occasions', hint: 'Needs other people. Never forced to complete.' },
	reminder: {
		label: 'reminder',
		unit: '',
		hint: 'A standing sentence. Nothing to start, nothing to finish — read it, and retire it when it is true and boring.'
	}
};

/** Status colours. `open` must never read as `locked` — that distinction is the
 * whole point of soft edges. */
export const statusTone: Record<NodeStatus, string> = {
	locked: 'text-stone-700',
	open: 'text-stone-400',
	available: 'text-stone-300',
	sealed: 'text-stone-500',
	active: 'text-stone-100',
	done: 'text-emerald-500',
	maintenance: 'text-amber-500',
	standing: 'text-stone-400'
};

/** What each season is called, and what it claims about your time. */
export const seasons: Record<SeasonState, { label: string; hint: string; tone: string }> = {
	high: {
		label: 'in season',
		hint: 'Acquiring. The full board, or the strands this season names.',
		tone: 'text-emerald-300 border-emerald-500/50'
	},
	low: {
		label: 'holding',
		hint: 'Not acquiring. Only what is about to go stale appears at all.',
		tone: 'text-amber-300/80 border-amber-500/40'
	},
	off: {
		label: 'parked',
		hint: 'Nothing decays here, so nothing is owed and nothing shows.',
		tone: 'text-stone-500 border-stone-700'
	}
};

/** Minutes out of a `min_each` string, or null when it names no number
 * ("one working day", "ongoing"). Never guesses — an unparseable contract is
 * reported as unquantified rather than silently counted as zero. */
export function minutesOf(minEach: string): number | null {
	const m = /^(\d+)\s*min/.exec(minEach ?? '');
	return m ? Number(m[1]) : null;
}

export function formatMinutes(total: number): string {
	const h = Math.floor(total / 60);
	const m = Math.round(total % 60);
	return h ? `${h}h ${String(m).padStart(2, '0')}m` : `${m}m`;
}

/** What today costs, added up from the `min_each` you typed.
 *
 * Not a score and not advice — arithmetic on declared data, which is the only
 * kind of number this app is willing to show. It exists because the daily cost
 * of the board was the one input that was never visible, and six domains
 * acquiring at once came to ten hours a day without ever saying so. */
export function declaredLoad(domains: DomainView[]): {
	minutes: number;
	unquantified: number;
	nodes: number;
} {
	let minutes = 0;
	let unquantified = 0;
	let nodes = 0;
	for (const d of domains) {
		if (!d.due_today) continue;
		for (const n of d.active_nodes) {
			nodes += 1;
			const m = minutesOf(n.min_each);
			if (m === null) unquantified += 1;
			else minutes += m;
		}
	}
	return { minutes, unquantified, nodes };
}

export const shapeBlurb: Record<DomainShape, string> = {
	ladder: 'one rung at a time',
	strands: 'parallel strands',
	cycles: 'projects, with craft feeding them'
};
