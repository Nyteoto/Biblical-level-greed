// The whole of what the page says to the server.
//
// One file, because the Portal has one subject — today — and every route is a
// question about it. The shapes mirror `backend/app/main.py`; `EXPECTED_API`
// is the number both sides have to agree on (see `version.py`).

async function call<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(`/api${path}`, {
		headers: { 'content-type': 'application/json' },
		...init
	});
	if (!res.ok) {
		let detail = await res.text();
		try {
			detail = JSON.parse(detail).detail ?? detail;
		} catch {
			/* not JSON; the text is the message */
		}
		throw new ApiError(res.status, detail);
	}
	return res.json() as Promise<T>;
}

/** A refusal, with the status the server chose. The Portal's refusals are
 *  part of the fiction — "the day has ended" is a 410 — so the page reads the
 *  status rather than parsing the words. */
export class ApiError extends Error {
	constructor(
		readonly status: number,
		message: string
	) {
		super(message);
	}
}

const post = <T>(path: string, body?: unknown) =>
	call<T>(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) });

// ── The Portal ────────────────────────────────────────────────────────────

export type Phase = 'unborn' | 'awake' | 'sitting' | 'sealed' | 'terminated';

export interface DayMedia {
	ref: string;
	kind: 'image' | 'video';
}

export interface Portal {
	now: string;
	day: string;
	instance: number;
	phase: Phase;
	/** Why a terminated day ended: `left`, `silent`, `deadline`, `corrupt`, or
	 *  null when nobody woke at all. */
	reason: string | null;
	window: { open: string; close: string; is_open: boolean };
	/** Seconds a sitting may go unheard before it is over. */
	grace: number;
	max_media: number;
	selfie: string | null;
	media: DayMedia[];
	/** The last sealed Instance before today, if any, and the day it lived. */
	previous: number | null;
	previous_day: string | null;
	/** When today's sitting began, while one is open. */
	began: string | null;
	/** How many Instances were terminated since `previous`. */
	failed: number;
	remark: string;
}

export interface RecordMedia extends DayMedia {
	caption: string;
}

export interface SealedRecord {
	template: number;
	instance: number;
	day: string;
	selfie: string;
	media: RecordMedia[];
	body: string;
	wish: string;
	signature: string;
	mood: number;
	sitting: { began: string; sealed: string };
	/** Whether a print exists at `/api/portal/pdf/{instance}`. */
	pdf: boolean;
	/** The sheet this one was filed on top of. */
	follows: { instance: number; day: string } | null;
}

export interface Draft {
	body: string;
	wish: string;
	signature: string;
	mood: number | null;
	captions: Record<string, string>;
}

export const getPortal = () => call<Portal>('/portal');
export const takeSelfie = (ref: string) => post<Portal>('/portal/selfie', { ref });
export const getLatest = () => call<{ record: SealedRecord | null }>('/portal/latest');
export const getOwnRecord = (n: number) => call<{ record: SealedRecord }>(`/portal/record/${n}`);
export const beginSitting = () => post<Portal & { token: string }>('/portal/sitting');
export const beat = (token: string) => post<{ ok: boolean; close: string }>('/portal/beat', { token });
export const attachMedia = (token: string, ref: string) =>
	post<Portal>('/portal/media', { token, ref });
export const detachMedia = (token: string, ref: string) =>
	post<Portal>('/portal/media/detach', { token, ref });
export const commit = (token: string, draft: Draft) =>
	post<Portal & { record: SealedRecord; printed: boolean }>('/portal/commit', { token, ...draft });

/** Sent as the page goes. `sendBeacon` because it is the one request a
 *  browser promises to deliver after `pagehide`; it posts text, so the token
 *  goes as the whole body. */
export function leave(token: string): void {
	navigator.sendBeacon('/api/portal/leave', new Blob([token], { type: 'text/plain' }));
}

export const pdfUrl = (n: number) => `/api/portal/pdf/${n}`;
export const mediaUrl = (ref: string) => `/media/${ref}`;
export const viewUrl = (ref: string) => `/media/${ref.replace(/\.[^./]+$/, '.view.jpg')}`;

// ── Media ─────────────────────────────────────────────────────────────────

export interface MediaUpload {
	ok: boolean;
	/** The original, byte for byte. */
	url: string;
	/** Its path under data/media — what the day and the Record hold. */
	path: string;
	/** The display copy, or the original again when there is no copy. */
	view_url: string;
	kind: 'image' | 'video' | '';
	bytes: number;
}

/**
 * Send one file. The body is the `File` itself, with no content-type of ours:
 * the browser streams it and the server streams it to disk, so this does not
 * grow with the size of what is being uploaded. `name` carries the filename
 * because the extension decides how the file is served later.
 */
export async function uploadMedia(
	file: File,
	onProgress?: (fraction: number) => void
): Promise<MediaUpload> {
	// XHR rather than fetch for the one thing fetch still cannot do: report
	// upload progress. A two-minute clip on a phone is long enough to need it.
	return new Promise((resolve, reject) => {
		const xhr = new XMLHttpRequest();
		xhr.open('POST', `/api/media?name=${encodeURIComponent(file.name)}`);
		xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(e.loaded / e.total);
		xhr.onload = () => {
			if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
			else {
				let detail = xhr.responseText;
				try {
					detail = JSON.parse(detail).detail ?? detail;
				} catch {
					/* keep the text */
				}
				reject(new ApiError(xhr.status, detail));
			}
		};
		xhr.onerror = () => reject(new ApiError(0, 'the upload did not reach the server'));
		xhr.send(file);
	});
}

/** Draw one frame of a video to a JPEG. Null whenever the browser will not.
 *
 *  1920 on the long edge, not a thumbnail's 640: this frame is what the
 *  printed Record carries in the clip's place, and it is printed at half the
 *  width of an A4 page. */
export async function posterFor(file: File, edge = 1920): Promise<Blob | null> {
	const url = URL.createObjectURL(file);
	const video = document.createElement('video');
	video.muted = true;
	// Both are required or iOS refuses to decode without a user gesture.
	video.playsInline = true;
	video.preload = 'metadata';
	video.src = url;

	try {
		await new Promise<void>((resolve, reject) => {
			const fail = () => reject(new Error('cannot decode'));
			video.onloadedmetadata = () => resolve();
			video.onerror = fail;
			setTimeout(fail, 5000);
		});

		// A frame from the very start is often black. One second in, or the
		// midpoint of anything shorter.
		await new Promise<void>((resolve, reject) => {
			const fail = () => reject(new Error('cannot seek'));
			video.onseeked = () => resolve();
			video.onerror = fail;
			setTimeout(fail, 5000);
			video.currentTime = Math.min(1, (video.duration || 2) / 2);
		});

		const scale = Math.min(1, edge / Math.max(video.videoWidth, video.videoHeight));
		const canvas = document.createElement('canvas');
		canvas.width = Math.max(1, Math.round(video.videoWidth * scale));
		canvas.height = Math.max(1, Math.round(video.videoHeight * scale));
		const ctx = canvas.getContext('2d');
		if (!ctx) return null;
		ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

		return await new Promise<Blob | null>((resolve) =>
			canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.92)
		);
	} catch {
		return null;
	} finally {
		video.src = '';
		URL.revokeObjectURL(url);
	}
}

/** Post a captured frame into the clip's display-copy slot. Best effort. */
export async function sendPoster(ref: string, poster: Blob): Promise<void> {
	try {
		await fetch(`/api/media?poster_for=${encodeURIComponent(ref)}`, {
			method: 'POST',
			body: poster
		});
	} catch {
		/* a clip without a poster is still a clip */
	}
}

// ── The machine ───────────────────────────────────────────────────────────

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

/** Bumped with `API_VERSION` in `backend/app/version.py`. */
export const EXPECTED_API = 10;

export const getApiVersion = () => call<{ api: number; since: string }>('/version');

export const restartServer = () => call<{ ok: boolean; unit: string }>('/restart', { method: 'POST' });
