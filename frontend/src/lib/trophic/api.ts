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
	/** `@place`. Captured like a pattern and, like one, pointing at nothing:
	 *  only `folders` decides where an entry lives. */
	places: string[];
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
	places: string[];
}

export interface Folder {
	id: string;
	name: string;
	color: string;
	/** The folder's standing description, and one picture for it. Both derived
	 *  from the log like everything else; empty means never written. */
	overview?: string;
	overview_media?: string;
	created_ts: string;
	/** "active", "shipped", or "" for a folder with no lifecycle — an interest
	 *  you keep rather than a project you finish. */
	state: string;
	/** How many entries resolve into it — tagged in or filed in by hand,
	 *  counted once. Derived on every read, like membership itself. */
	entry_count: number;
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

/** A folder seen through one year. Everything below is a derived read — no row
 *  anywhere records the pairing, which is what lets the year setting be a
 *  switch rather than a migration. */
export interface Album extends Folder {
	/** Entries in this album *this year*. `entry_count` on a plain Folder is
	 *  all of history; both are offered because the card is about the year and
	 *  the sidebar is about the project. */
	all_time_count: number;
	media_count: number;
	/** Twelve entry counts, January first. The sparkline and the month spine
	 *  read the same list — one lying down, one standing up. */
	volumes: number[];
	/** `Feb–May`, or `Feb`. Empty when the album is empty. */
	months: string;
	chapters: number;
	/** The newest few attachments — the card's mosaic. */
	lead: string[];
	/** The group heading this card sits under this year, or "" for the loose
	 *  grid above them. Cosmetic — it files nothing and gates nothing. */
	group: string;
}

/** A contiguous run of months inside one album-year, named from the user's own
 *  commonest tag or pattern inside it. Derived on every read. */
export interface Chapter {
	name: string;
	range: string;
	first_month: number;
	last_month: number;
	entries: number;
}

export interface Shelf {
	year: string | null;
	/** Every year the log has anything in, newest first. The year rail. */
	years: string[];
	albums: Album[];
	/** The year's group headings, in shelf order — first named, first drawn.
	 *  Empty on the all-years shelf, which has no groups at all: a group is an
	 *  arrangement *of a year*. */
	groups: string[];
	unfiled: number;
	entries: number;
	media: number;
	previous: { year: string; entries: number } | null;
	/** Where the newest line in this year is, for `Opens on: latest day`.
	 *  `folder` is null when that line is unfiled, which is not a special case:
	 *  the unfiled pile is an album you can be taken back to like any other. */
	latest: { folder: string | null; day: string; ts: string } | null;
}

export interface AlbumView {
	/** Null for the unfiled pile, which is an album you can open like any
	 *  other but is not a folder. */
	folder: Folder | null;
	year: string | null;
	entries: Entry[];
	volumes: number[];
	chapters: Chapter[];
	media_count: number;
	sentiments: { name: string; count: number }[];
	/** Which shelf group this folder sits in *this year*, or "" for the loose
	 *  grid. Per-year, so the same folder can be filed differently next year. */
	group: string;
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

/** The year shelf. `year` of `'all'` — which is what the yearly-restart switch
 *  turned off sends — drops the filter without changing the shape. */
export const getShelf = (year: string) => call<Shelf>(`/shelf?year=${year}`);

/** One album, one year. A null folder is the unfiled pile. */
export const getAlbum = (folder: string | null, year: string) =>
	call<AlbumView>(`/album?folder=${folder ?? 'unfiled'}&year=${year}`);

/** Throw the capture index away and replay the log. Safe by construction —
 *  the index is a projection and nothing else. */
export const reindex = () =>
	call<{ indexed: number; warnings: string[] }>('/reindex', { method: 'POST' });

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

/** Rename, move along its life, map tags, unmap tags — any combination, one
 *  request. `state: ''` is a value, not an omission: it clears the state. */
export const patchFolder = (
	id: string,
	change: {
		name?: string;
		state?: string;
		add_tags?: string[];
		remove_tags?: string[];
		/** The overview's two halves. Empty is a real value for both — a cleared
		 *  description, or a removed picture. */
		overview?: string;
		overview_media?: string;
	}
) => call<{ folder: Folder }>(`/folders/${id}`, { method: 'PATCH', body: JSON.stringify(change) });

/** Put a folder under a named heading on one year's shelf, or take it out of
 *  one with an empty `name`. Answers with the whole shelf, because one move
 *  can create a heading or empty the last one out of existence and a
 *  folder-shaped reply would say neither. */
export const setFolderGroup = (id: string, year: string, name: string) =>
	call<Shelf & { version: number }>(`/folders/${id}/group`, {
		method: 'PUT',
		body: JSON.stringify({ year, name })
	});

/** Rename one year's group, carrying every folder under it. Renaming onto a
 *  name the year already uses merges the two. */
export const renameGroup = (year: string, name: string, to: string) =>
	call<Shelf & { version: number }>('/groups/rename', {
		method: 'POST',
		body: JSON.stringify({ year, name, to })
	});

/** Take a group off one year's shelf. Its folders return to the loose grid; no
 *  folder and no entry is touched. */
export const deleteGroup = (year: string, name: string) =>
	call<Shelf & { version: number }>('/groups/delete', {
		method: 'POST',
		body: JSON.stringify({ year, name })
	});

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
