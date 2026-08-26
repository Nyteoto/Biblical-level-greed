/**
 * The machine's half of the API: the disk, the backup, and the version handshake.
 *
 * Everything the *journal* talks to lives in `$lib/trophic/api.ts`. This file
 * is what is left after the tech tree went — the endpoints that are about the
 * installation rather than about anything the user wrote, which is the same
 * line `backend/app/` draws on the server.
 */

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

/** When the copy on the other disk was last made, and whether one is running.
 *  `last` is the ISO timestamp `backup.sh` writes into the destination on
 *  success — the only fact about a backup worth reporting, and the one a
 *  silent timer never answers. */
export interface BackupStatus {
	destination: string;
	source: string;
	last: string | null;
	seconds_ago: number | null;
	running: boolean;
	result: { ok: boolean; message: string } | null;
}

export const getBackup = () => call<BackupStatus>('/backup');

/** Start a run and return immediately; poll `getBackup`. Every refusal
 *  `backup.sh` makes is still made — this starts the script, it does not
 *  reimplement any part of it. */
export const runBackup = () => call<BackupStatus>('/backup', { method: 'POST' });

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

/**
 * The API this build was written against. Bumped in lockstep with
 * `backend/app/version.py` whenever a route, a payload or an event kind changes
 * in a way this code depends on.
 *
 * The browser reloads its own files off disk, so the frontend is always
 * current. The Python process is not: a long-running service keeps serving the
 * old code until something restarts it, and the app in front of it then looks
 * broken for reasons that are nowhere in the source. This is the number that
 * makes that visible instead of mysterious.
 */
export const EXPECTED_API = 6;

export const getApiVersion = () => call<{ api: number; since: string }>('/version');

export const restartServer = () => call<{ ok: boolean; unit: string }>('/restart', { method: 'POST' });
