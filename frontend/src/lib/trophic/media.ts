// Attaching files to a capture: uploading them, and finding a poster frame.
//
// Kept out of the component for the reason `capture-bar.ts` is: the component
// owns the DOM and the timers, the module owns the decisions. This one is not
// pinned by a corpus — the source never had video — but the seam is the same
// and it is where the awkward parts live.
//
// **Posters are made in the browser, not on the server.** A server-side frame
// grab means ffmpeg, and ffmpeg would have to be installed on both halves of a
// dual-boot machine for the app to behave the same under either. The browser
// has already decoded enough of the file to show a preview, so it can draw one
// frame to a canvas and post that instead. Every step of it is allowed to
// fail: a codec the browser will not decode just means the clip has no poster,
// and the log falls back to `preload="metadata"`.

import { mediaUrl } from './api';
import type { Entry } from './api';

/** One attachment, plus the line it was written beside. The pair the grid and
 *  the lightbox both deal in: a tile has to know what to open, and the viewer
 *  has to know what to caption it with. */
export type Shot = { ref: string; entry: Entry };

export type Attachment = {
	/** Local id, so a chip can be removed before anything is uploaded. */
	key: string;
	file: File;
	kind: 'image' | 'video';
	/** Object URL for the pending-chip preview. Revoked when the chip goes. */
	preview: string;
	/** Set once uploaded — the path the entry will carry. */
	ref?: string;
	/** 0..1 while uploading. */
	progress: number;
	error?: string;
};

export type Uploaded = {
	ok: boolean;
	url: string;
	path: string;
	view_url: string;
	kind: 'image' | 'video' | '';
	bytes: number;
};

const IMAGE_EXT = /\.(jpe?g|png|gif|webp|heic|heif|avif)$/i;
const VIDEO_EXT = /\.(mp4|mov|m4v|webm)$/i;

export function kindOf(file: File): 'image' | 'video' | '' {
	if (file.type.startsWith('image/') || IMAGE_EXT.test(file.name)) return 'image';
	if (file.type.startsWith('video/') || VIDEO_EXT.test(file.name)) return 'video';
	// An iPhone sometimes reports an empty type for HEIC; the extension is the
	// fallback, and the server refuses anything neither test recognises.
	return '';
}

/** Is this stored path a clip? Extension only — a `media/…` reference carries
 *  no MIME type, and the writer picked the extension from the kind, so it is
 *  as reliable here as `kindOf` is on the way in. */
export function isVideo(ref: string): boolean {
	return VIDEO_EXT.test(ref);
}

/**
 * What a plate does when its display copy will not load.
 *
 * Every screen that draws media had its own copy of this, and they had drifted
 * into three different endings: the contact sheet fell back to a clean tinted
 * plate, the lead photograph and the ribbon left the browser's broken-image
 * glyph sitting in the frame, and the shelf's mosaic retried the *original* of
 * a clip — pointing an `<img>` at a two-gigabyte `.mov`, which is a download
 * rather than a fallback. One rule now, in one place:
 *
 *   - a `.view.jpg` that fails on an **image** steps down to the original, once
 *     (Pillow may not have been able to write a display copy);
 *   - anything else gives up and leaves the tinted plate, which is honest —
 *     a clip has no poster until one is captured, and there is nothing to show
 *     until it is opened.
 */
export function plateFallback(event: Event, ref: string): void {
	const el = event.currentTarget as HTMLImageElement;
	if (el.src.endsWith('.view.jpg') && !isVideo(ref)) {
		el.src = mediaUrl(ref);
		return;
	}
	el.style.visibility = 'hidden';
}

export function attach(file: File): Attachment | null {
	const kind = kindOf(file);
	if (!kind) return null;
	return {
		key: `${file.name}:${file.size}:${file.lastModified}:${Math.random()}`,
		file,
		kind,
		preview: URL.createObjectURL(file),
		progress: 0
	};
}

export function release(a: Attachment) {
	URL.revokeObjectURL(a.preview);
}

/**
 * Upload one file. `XMLHttpRequest` rather than `fetch` for one reason:
 * `fetch` cannot report upload progress, and a two-minute video with no
 * feedback looks like a hang.
 */
export function upload(
	file: File,
	onprogress?: (fraction: number) => void,
	/** Where this is being filed, for the stored filename only — see
	 *  `media.py`. A snapshot of the upload, not a claim about membership. */
	folder = ''
): Promise<Uploaded> {
	return new Promise((resolve, reject) => {
		const request = new XMLHttpRequest();
		const query =
			`name=${encodeURIComponent(file.name)}` +
			(folder ? `&folder=${encodeURIComponent(folder)}` : '');
		request.open('POST', `/api/media?${query}`);
		request.upload.onprogress = (e) => {
			if (e.lengthComputable) onprogress?.(e.loaded / e.total);
		};
		request.onload = () => {
			if (request.status >= 200 && request.status < 300) {
				try {
					resolve(JSON.parse(request.responseText) as Uploaded);
				} catch {
					reject(new Error('the server sent something that was not JSON'));
				}
			} else {
				reject(new Error(request.responseText || `upload failed (${request.status})`));
			}
		};
		request.onerror = () => reject(new Error('the connection dropped mid-upload'));
		request.send(file);
	});
}

/** Draw one frame of a video to a JPEG. Null whenever the browser will not. */
export async function posterFor(file: File, edge = 640): Promise<Blob | null> {
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
			canvas.toBlob((blob) => resolve(blob), 'image/jpeg', 0.8)
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

// The queue that actually runs these lives in `uploads.svelte.ts`. There used
// to be a second copy of it here — `uploadAll`, same loop, same "attach before
// the poster" rule, taking `attach` and `onchange` as parameters — with no
// call site anywhere. Two implementations of the file-loss path, one of them
// never executed and therefore never wrong in a way anyone would notice.
