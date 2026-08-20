// Uploads in flight, for the whole app rather than one screen.
//
// This used to be state on the capture page, which meant the progress line
// disappeared the moment you navigated to the log — and since a big clip takes
// minutes, the natural thing to do while waiting is exactly that. The upload
// itself never stopped (an XHR outlives a client-side navigation), but with
// nothing on screen saying so it read as cancelled, which is worse than a
// cancellation you can see.
//
// So the queue lives here, at module scope, and the shell renders it. It is
// the one piece of app-wide state Trophic has, and it earns it: a two-gigabyte
// upload is the only thing in this app that outlives the screen that started
// it.
//
// ## A failure is held, not swallowed
//
// There are two lists, and the second one is the whole point of this file's
// second draft. The first version set `item.error` in a `catch` and then
// removed the item from the queue in the `finally` immediately after, which
// meant `failures()` — filtering that same queue — could never return
// anything, and nothing called it in any case. A photograph that failed to
// upload simply never appeared on the entry, with no message on any screen
// and its preview already revoked.
//
// That is the media half of the thing this app is not allowed to do. A line
// refused by the server goes back in the capture box; a file refused by it has
// to be held the same way. So a failed upload moves to `failed` and stays
// there — with its `File` intact, which is what makes the retry real rather
// than an apology — until it is sent or the user lets it go. The blob URL is
// revoked when it leaves that list and not before, because the thumbnail has
// to survive long enough to say *which* picture did not make it.

import { attachMedia } from './api';
import { posterFor, release, sendPoster, upload, type Attachment } from './media';

/** One file that did not go up, and everything needed to try it again. */
export type FailedUpload = {
	item: Attachment;
	/** The entry it belonged to. Still in the log — the line went in first. */
	entryId: string;
	folder: string;
};

const queue = $state<Attachment[]>([]);
const failed = $state<FailedUpload[]>([]);

export const uploads = {
	/** Everything still going up, oldest first. */
	get items(): Attachment[] {
		return queue;
	},
	get count(): number {
		return queue.length;
	},
	/** 0..1 across the whole queue, so one bar can stand for all of it. */
	get progress(): number {
		if (queue.length === 0) return 0;
		return queue.reduce((sum, i) => sum + i.progress, 0) / queue.length;
	},
	/** Files that did not make it. Held until sent or dismissed. */
	get failed(): FailedUpload[] {
		return failed;
	}
};

/**
 * Send files for an entry that is already written, attaching each as it lands.
 *
 * Not awaited by the caller and deliberately so: the line is already in the
 * log and the point is that you can carry on. Errors are surfaced on the item
 * rather than thrown, because one bad file should not take the others with it.
 */
export async function startUploads(
	entryId: string,
	items: Attachment[],
	/** Where the line these files belong to was filed, for the filename only. */
	folder = ''
): Promise<void> {
	queue.push(...items);
	for (const item of items) {
		let kept = false;
		try {
			item.error = undefined;
			const done = await upload(item.file, (fraction) => (item.progress = fraction), folder);
			item.ref = done.path;
			item.progress = 1;

			// Attach before the poster: the clip is safe on the entry either
			// way, and a poster that fails must not cost you the video.
			await attachMedia(entryId, [done.path]);

			if (item.kind === 'video') {
				const poster = await posterFor(item.file);
				if (poster) await sendPoster(done.path, poster);
			}
		} catch (e) {
			// Held rather than released. The `File` is still in memory, so this
			// is a retry and not a condolence; the preview is still live, so
			// the message can show which picture it is talking about.
			item.error = e instanceof Error ? e.message : 'upload failed';
			item.progress = 0;
			failed.push({ item, entryId, folder });
			kept = true;
		} finally {
			if (!kept) release(item);
			const at = queue.indexOf(item);
			if (at >= 0) queue.splice(at, 1);
		}
	}
}

/**
 * Try the failed ones again, each back to the entry it belonged to.
 *
 * The list is emptied first and refilled by `startUploads` for whatever fails
 * a second time, so a retry that half works leaves exactly the half that did
 * not. Grouped by entry because `startUploads` attaches to one.
 */
export function retryFailed(): void {
	const waiting = failed.splice(0, failed.length);
	const byEntry = new Map<string, FailedUpload[]>();
	for (const f of waiting) {
		const key = `${f.entryId} ${f.folder}`;
		const found = byEntry.get(key);
		if (found) found.push(f);
		else byEntry.set(key, [f]);
	}
	for (const group of byEntry.values()) {
		startUploads(
			group[0].entryId,
			group.map((f) => f.item),
			group[0].folder
		);
	}
}

/** Let them go. The originals are still on the user's disk — this drops the
 *  app's copy of the intention, not the file. */
export function dismissFailed(): void {
	for (const f of failed.splice(0, failed.length)) release(f.item);
}
