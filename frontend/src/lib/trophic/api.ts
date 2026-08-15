// Client for /api/capture. Mirrors backend/capture/api.py; nothing here is
// user-scoped, because there is one user and they are sitting at the machine.

export interface Entry {
	id: string;
	ts: string;
	day: string;
	/** What was typed. The log's only content. */
	raw_text: string;
	/** What is shown: directives and --todo stripped. Derived, not stored. */
	clean_text: string;
	folders: string[];
	times: string[];
	patterns: string[];
	todo_lines: number[];
	todo_done: number[];
	/** Folders this entry was filed into by hand. At most one, like the source. */
	manual_folders: string[];
	/** Files attached at capture time, as paths under data/media. */
	media: string[];
}

/** The two URLs a stored file has: the original, and what to draw. The display
 *  copy may not exist — for video it arrives only once a poster is captured —
 *  so anything using the second should fall back to the first on error. */
export const mediaUrl = (ref: string) => `/media/${ref}`;
export const mediaViewUrl = (ref: string) => `/media/${ref.replace(/\.[^.]+$/, '.view.jpg')}`;

export interface Vocab {
	folders: { id: string; name: string; color: string }[];
	tag_to_folder: Record<string, string>;
	tags: string[];
	times: string[];
	patterns: string[];
}

export interface Folder {
	id: string;
	name: string;
	color: string;
	created_ts: string;
	/** The tags that point here. A tag points at one folder at most. */
	tags: string[];
}

export interface FolderDetail {
	folder: Folder;
	entries: Entry[];
	sentiments: { name: string; count: number }[];
}

export interface UnassignedTag {
	tag: string;
	count: number;
}

export interface Reminder {
	entry_id: string;
	/** Line index within the entry that carried the `{time}`. */
	line: number;
	line_text: string;
	/** UTC ISO. Always UTC — see the backend's reminders table. */
	due_at: string;
}

/** The connection failed, as opposed to the server refusing. The capture
 *  screen treats the two differently: a refusal gives the text back, a dead
 *  connection queues the line and lets the user carry on. */
export class NetworkError extends Error {}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
	let res: Response;
	try {
		res = await fetch(`/api/capture${path}`, {
			headers: { 'content-type': 'application/json' },
			...init
		});
	} catch (e) {
		throw new NetworkError(e instanceof Error ? e.message : 'offline');
	}
	if (!res.ok) {
		let detail = await res.text();
		try {
			detail = JSON.parse(detail).detail ?? detail;
		} catch {
			/* a non-JSON body is the message */
		}
		throw new Error(detail);
	}
	return res.json() as Promise<T>;
}

export const getEntries = (params: { date?: string; from?: string; to?: string; limit?: number }) => {
	const q = new URLSearchParams();
	for (const [k, v] of Object.entries(params)) if (v != null) q.set(k, String(v));
	return call<{ entries: Entry[]; version: number }>(`/entries?${q}`);
};

/** Where a queued capture is replayed to. The retry queue stores a URL and a
 *  body rather than a call, so it has to know the absolute path. */
export const CAPTURE_URL = '/api/capture/entries';
export const captureBody = (raw_text: string, media: string[] = []) =>
	JSON.stringify({ raw_text, media });

export const capture = (raw_text: string, media: string[] = []) =>
	call<{ entry: Entry }>('/entries', {
		method: 'POST',
		body: captureBody(raw_text, media)
	});

export const toggleLine = (id: string, line: number) =>
	call<{ entry: Entry }>(`/entries/${id}`, {
		method: 'PATCH',
		body: JSON.stringify({ toggle_line: line })
	});

export const getDates = () => call<{ dates: Record<string, number> }>('/dates');

export const getVocab = () => call<Vocab>('/vocab');

/**
 * Read a CSV into the log. The file is sent whole and parsed on the backend —
 * the source parses in the browser only because it may have to encrypt before
 * the server sees anything, and there is no server to hide from here.
 */
export const importCsv = (csv: string) =>
	call<{ imported: number; skipped: number; header: string }>('/import', {
		method: 'POST',
		body: JSON.stringify({ csv })
	});

// ── Reminders ─────────────────────────────────────────────────────────────

export const getReminders = () => call<{ reminders: Reminder[] }>('/reminders');

export const dismissReminder = (entry_id: string, line: number) =>
	call<{ reminders: Reminder[] }>('/reminders/dismiss', {
		method: 'POST',
		body: JSON.stringify({ entry_id, line })
	});

// ── Folders ───────────────────────────────────────────────────────────────

export const getFolders = () => call<{ folders: Folder[] }>('/folders');

export const getFolder = (id: string) => call<FolderDetail>(`/folders/${id}`);

export const createFolder = (name: string, tags: string[] = []) =>
	call<{ folder: Folder }>('/folders', {
		method: 'POST',
		body: JSON.stringify({ name, tags })
	});

/** Rename, map tags, unmap tags — any combination, one request. */
export const patchFolder = (
	id: string,
	change: { name?: string; add_tags?: string[]; remove_tags?: string[] }
) => call<{ folder: Folder }>(`/folders/${id}`, { method: 'PATCH', body: JSON.stringify(change) });

export const deleteFolder = (id: string) => call<{ ok: boolean }>(`/folders/${id}`, { method: 'DELETE' });

export const getUnassignedTags = () =>
	call<{ tags: UnassignedTag[]; total: number }>('/tags/unassigned');

/** Hang files on an entry that is already written — the upload finished after
 *  the line went in, which is the normal case for anything large. */
export const attachMedia = (id: string, media: string[]) =>
	call<{ entry: Entry }>(`/entries/${id}`, {
		method: 'PATCH',
		body: JSON.stringify({ attach_media: media })
	});

/** File an entry into a folder by hand, or pass null to unfile it. */
export const assignEntry = (id: string, folder: string | null) =>
	call<{ entry: Entry }>(`/entries/${id}`, {
		method: 'PATCH',
		body: JSON.stringify({ assign_folder: folder })
	});
