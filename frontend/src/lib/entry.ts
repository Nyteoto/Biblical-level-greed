/** Turning an `entry` line into something you can click.
 *
 * The trees ship 471 of these and not one is a bare URL — they are titles and
 * search strings, on purpose: a search for "40 essential rudiments vic firth"
 * still works in five years and a link to it probably does not. That decision
 * stays; this file only makes the same strings openable.
 *
 * The important rule is that **most lines are not resources at all.** `Method:`,
 * `Rule:`, `Practice:` and most unlabelled lines are advice — "Set the metronome
 * on 2 and 4 only" is not a thing to go and open, and linking it to a search
 * would be noise dressed up as help. Only lines that name something findable
 * become links.
 */

/** Where a title or a search term goes when clicked. One constant, so changing
 * engines is a one-line edit. */
const SEARCH = 'https://www.google.com/search?q=';

/** Labels that introduce something you can actually go and get. */
const RESOURCE_LABELS = new Set([
	'free',
	'book',
	'paid',
	'listen',
	'watch',
	'hardware',
	'find',
	'app',
	'tool',
	'course'
]);

/** Labels that introduce advice. Never linked — see the note above. */
const ADVICE_LABELS = new Set([
	'method',
	'rule',
	'practice',
	'note',
	'reality',
	'warning',
	'gate'
]);

// Deliberately a fixed list rather than "any dot-separated word". The entries
// are full of things a permissive pattern would happily turn into broken links:
// `6.002`, `Vol 1.`, `HSK 3.0` — and `scipy.signal.firwin`, which is a Python
// module path that looks exactly like a hostname. Every TLD below actually
// occurs in the shipped trees.
const TLD = 'com|org|net|edu|io|dev|app|co|uk|be|pub|ai|fm|tv|me|info|cn|us|google';
const URL_RE = new RegExp(
	`(https?://[^\\s)]+)|(\\b(?:[a-z0-9-]+\\.)+(?:${TLD})\\b(?:/[^\\s,;)]*)?)`,
	'gi'
);

const LABEL_RE = /^([A-Za-z][A-Za-z ,'’]{0,20}?):\s*/;

export interface Segment {
	text: string;
	/** Absent for plain prose. */
	href?: string;
}

export const searchFor = (term: string) => SEARCH + encodeURIComponent(term.trim());

function label(line: string): string {
	const found = LABEL_RE.exec(line);
	// "Paid, worth it:" — the first word is the label, the rest is editorial.
	return found ? found[1].split(/[ ,]/)[0].toLowerCase() : '';
}

/** Split out any literal URLs or bare domains. Returns null when there are none,
 * so the caller can fall back to linking a title. */
function linkUrls(line: string): Segment[] | null {
	const out: Segment[] = [];
	let last = 0;
	URL_RE.lastIndex = 0;
	for (let m = URL_RE.exec(line); m; m = URL_RE.exec(line)) {
		if (m.index > last) out.push({ text: line.slice(last, m.index) });
		const raw = m[0];
		out.push({ text: raw, href: raw.startsWith('http') ? raw : `https://${raw}` });
		last = m.index + raw.length;
	}
	if (!out.length) return null;
	if (last < line.length) out.push({ text: line.slice(last) });
	return out;
}

/** The part of a resource line worth searching for.
 *
 * These lines name a thing and then describe it, and the switch happens at an
 * em dash or a full stop: "Vic Firth 40 Essential Rudiments hub — all 40,
 * official PAS list" wants the first half; "Bryant and O'Hallaron, Computer
 * Systems: A Programmer's Perspective (CS:APP). TYCS's own pick" wants the
 * first sentence.
 *
 * Returns "" when what is left is too long to be a name. A 150-character
 * "title" is a paragraph of advice that happened to start with `Hardware:`, and
 * searching for it would return nothing useful — better no link than a link
 * that wastes the tap. */
const MAX_TITLE = 72;

function title(rest: string): string {
	const cut = rest.split('—')[0].split(' - ')[0].split(/\.\s/)[0];
	const trimmed = cut.replace(/[.,;:\s]+$/, '').trim();
	return trimmed.length > MAX_TITLE ? '' : trimmed;
}

/**
 * One entry line, split into plain text and clickable spans.
 *
 * - a URL or bare domain anywhere in the line links directly
 * - `Search: a, b, c` gives one search link per term
 * - a resource label links its title
 * - anything else is left as prose
 */
export function parseEntry(line: string): Segment[] {
	const direct = linkUrls(line);
	if (direct) return direct;

	const kind = label(line);
	const rest = line.slice(LABEL_RE.exec(line)?.[0].length ?? 0);

	if (kind === 'search') {
		// Comma-separated alternatives, each its own search — they are different
		// queries, not one long one.
		const out: Segment[] = [{ text: line.slice(0, line.length - rest.length) }];
		rest.split(',').forEach((term, i) => {
			if (i) out.push({ text: ', ' });
			const clean = term.trim();
			if (clean) out.push({ text: clean, href: searchFor(clean) });
		});
		return out;
	}

	if (RESOURCE_LABELS.has(kind)) {
		const named = title(rest);
		if (named.length > 2) {
			const at = line.indexOf(named);
			return [
				{ text: line.slice(0, at) },
				{ text: named, href: searchFor(named) },
				{ text: line.slice(at + named.length) }
			].filter((s) => s.text);
		}
	}

	if (ADVICE_LABELS.has(kind) || !kind) return [{ text: line }];
	return [{ text: line }];
}

/** Just the openable parts of a node's entry, deduped — the compact strip that
 * stays on the card after the first session, when you no longer need telling
 * where to start and only want the thing opened. */
export function entryLinks(entry: string[]): Segment[] {
	const seen = new Set<string>();
	const out: Segment[] = [];
	for (const line of entry) {
		for (const seg of parseEntry(line)) {
			if (!seg.href || seen.has(seg.href)) continue;
			seen.add(seg.href);
			out.push(seg);
		}
	}
	return out;
}
