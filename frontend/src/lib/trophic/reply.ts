/**
 * `--reply`: answering the reminder standing above the capture box.
 *
 * Ported from `CaptureClient.tsx`, which is the only place the source
 * implements it. Three rules, all of them here so `verify:ui` can hold them:
 *
 *   - **It only counts at the front of the draft, and it needs a space after.**
 *     `/^--reply\s+/i` — the source's own regex. `--reply` on its own is not a
 *     reply, it is someone halfway through typing one, and a `--reply`
 *     mentioned mid-sentence is prose.
 *   - **The command is stripped before the line is stored.** What you typed it
 *     *for* is the entry; the command was addressed to the app. This is the
 *     one place this port lets something be taken off the raw line, and it is
 *     safe because the thing it encoded — which entry is being answered — is
 *     kept as a field on the event rather than thrown away. The alternative
 *     was storing `--reply` and stripping it in `clean_text`, which 40 parser
 *     fixtures forbid: they pin `cleanText` as keeping it.
 *   - **A reply is an ordinary entry otherwise.** `{time}` on the stripped text
 *     resolves as usual, so an answer can start the next round of the
 *     conversation. The source resolves reminders on the stripped text for
 *     exactly this reason and says so in a comment.
 *
 * What is *not* here: whether there is anything to reply to. That needs the
 * reminder standing above the box, so it lives on the screen — see the submit
 * path in `(capture)/+page.svelte`.
 */

/** The source's regex, unchanged. Case-insensitive, anchored, space required. */
export const REPLY_RE = /^--reply\s+/i;

/** Whether this draft is addressed to the reminder above the box. */
export function isReply(draft: string): boolean {
	return REPLY_RE.test(draft.trim());
}

/** The thought, without the command. Trimmed, because the space the regex
 *  required is not part of what was written. */
export function stripReply(draft: string): string {
	return draft.trim().replace(REPLY_RE, '').trim();
}
