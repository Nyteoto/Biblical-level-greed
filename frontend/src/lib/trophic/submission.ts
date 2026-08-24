/**
 * Sending a capture: what happens to the text, and what happens to the files.
 *
 * Why it is shaped this way
 * -------------------------
 * **Losing a captured thought is the one thing this app cannot do**, and until
 * this module existed the code that made that true had no interface. It lived
 * inside a 127-line `submit()` in the capture route, tangled with a shake
 * animation, a slide-out, a timer racing the server's answer and a
 * sessionStorage write — so the only way to exercise it was to drive a
 * browser, and the two halves of it were reconciled by hand:
 * `retry-queue.ts` queues an entry *body* and `uploads.svelte.ts` queues
 * *files*, and neither knows about the other. When the connection drops the
 * line has to be queued and the files have to be given back, because the queue
 * replays a body and there is no entry id for an upload to attach to yet. That
 * pairing is the whole substance of the failure path and it was two statements
 * next to each other in a component.
 *
 * It is one decision now, with three answers: `sent`, `queued`, `refused`.
 *
 * **The environment is injected**, and not only for the usual reason. This
 * file has to stay runnable under `verify-ui.ts`'s type-stripping loader,
 * which cannot execute runes — so it can import types from `uploads.svelte.ts`
 * but never the module itself. The caller passes the four things that touch
 * the outside world, exactly as `retry-queue.ts` takes a `QueueEnv`, and
 * `localChecks` drives this with all four faked.
 *
 * What is *not* here: the shake, the slide, the flash, the draft, the focus,
 * the vocabulary re-read and the banner. Those are what the screen does about
 * an outcome, and a different screen could reasonably do something else.
 */
import { CAPTURE_URL, NetworkError, captureBody, type Entry } from './api';
import { withPinnedTag } from './pinned';
import type { Attachment } from './media';

/** A capture as the user composed it, with the command already taken off. */
export type Draft = {
	/** The thought. `--reply` stripped; the pin's tag not yet added. */
	text: string;
	/** Picked but not yet uploaded. May be empty; a line is enough. */
	files: Attachment[];
	/** The folder pinned in the bar, if one is — appended to the *raw line*, so
	 *  a pinned capture is byte-identical to one you tagged yourself. `null` is
	 *  as good as absent: nothing is pinned, so nothing is appended. */
	pinTag?: string | null;
	/** The entry this answers, when the draft was a `--reply`. */
	answering?: string;
};

export type Outcome =
	/** It is in the log. `entry` is what came back. */
	| { kind: 'sent'; entry: Entry }
	/** The connection was gone. The line is in the retry queue and will be
	 *  replayed; the files could not be and have been given back. */
	| { kind: 'queued'; pending: number; lostFiles: number }
	/** The server answered and said no. Nothing was written; the caller has to
	 *  put the text and the files back. */
	| { kind: 'refused'; message: string };

export type SubmitEnv = {
	capture(text: string, media: string[], replyTo?: string): Promise<{ entry: Entry }>;
	/** Start the background uploads for an entry that now exists. */
	upload(entryId: string, files: Attachment[], folder: string): void;
	/** Put a body in the retry queue. */
	enqueue(url: string, body: string): void;
	/** How many bodies are waiting, after the enqueue. */
	pending(): number;
	/** Hand a picked file back — revoke its object URL and forget it. */
	release(file: Attachment): void;
};

/**
 * The line as it will be stored: the thought with the pin's tag on it.
 *
 * Separate because the raw line is the thing membership is resolved from, and
 * "what exactly gets written" is worth being able to ask without sending
 * anything. Never add a folder id to the payload instead — that would be a
 * second kind of membership the fold cannot reproduce.
 */
export function lineFor(draft: Draft): string {
	return draft.pinTag ? withPinnedTag(draft.text, draft.pinTag) : draft.text;
}

/**
 * Send one draft. Never throws: every ending is an `Outcome`.
 *
 * The order matters and is the reason this is one function. The text goes
 * first and alone — a clip can take minutes and must never hold up the
 * thought — and the files follow it in the background, attaching themselves to
 * an entry that already exists. So there are exactly two failure shapes, and
 * they are not the same thing:
 *
 *   - **No connection.** Not the user's problem. The body is queued and
 *     replayed when the browser comes back, so the draft can stay gone. The
 *     files cannot go with it: the queue replays a body, not an upload, and
 *     there is no entry id to attach one to. They are released here rather
 *     than left holding object URLs for a send that will never happen, and
 *     `lostFiles` is how the caller knows to say so.
 *   - **A refusal from a server that answered.** The user's problem, and
 *     nothing was written. The files are *not* released — the caller is about
 *     to put them back in the bar with the text.
 */
export async function send(draft: Draft, env: SubmitEnv): Promise<Outcome> {
	const line = lineFor(draft);
	const files = draft.files;

	try {
		const { entry } = await env.capture(line, [], draft.answering);
		if (files.length > 0) {
			// The folder as the line was written: the pinned one, else the first
			// `<tag>` in it. A filename hint only — membership is still resolved.
			env.upload(entry.id, files, entry.folders?.[0] ?? '');
		}
		return { kind: 'sent', entry };
	} catch (e) {
		if (e instanceof NetworkError) {
			env.enqueue(CAPTURE_URL, captureBody(line, [], draft.answering));
			for (const file of files) env.release(file);
			return { kind: 'queued', pending: env.pending(), lostFiles: files.length };
		}
		return {
			kind: 'refused',
			message: e instanceof Error ? e.message : 'failed to save'
		};
	}
}
