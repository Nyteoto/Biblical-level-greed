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

import { attachMedia } from './api';
import { posterFor, release, sendPoster, upload, type Attachment } from './media';

const queue = $state<Attachment[]>([]);

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
	}
};

/**
 * Send files for an entry that is already written, attaching each as it lands.
 *
 * Not awaited by the caller and deliberately so: the line is already in the
 * log and the point is that you can carry on. Errors are surfaced on the item
 * rather than thrown, because one bad file should not take the others with it.
 */
export async function startUploads(entryId: string, items: Attachment[]): Promise<void> {
	queue.push(...items);
	for (const item of items) {
		try {
			const done = await upload(item.file, (fraction) => (item.progress = fraction));
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
			item.error = e instanceof Error ? e.message : 'upload failed';
		} finally {
			release(item);
			const at = queue.indexOf(item);
			if (at >= 0) queue.splice(at, 1);
		}
	}
}

/** Anything that failed, for a screen that wants to say so. */
export function failures(): Attachment[] {
	return queue.filter((i) => i.error);
}
