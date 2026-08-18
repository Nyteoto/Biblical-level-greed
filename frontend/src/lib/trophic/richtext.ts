/**
 * What an overview is allowed to contain.
 *
 * The field stores HTML, and this is the gate on both ends of it — what the
 * editor keeps when you paste, and what the card is willing to render. The
 * threat model is not an attacker: it is one person pasting from a web page and
 * dragging a stylesheet, a font stack and a colour palette into a screen that
 * is meant to be a single hue. Dropping every attribute is what keeps the
 * phosphor consistent; keeping a short tag list is what keeps it writing.
 *
 * In a module rather than in the component because two places need the same
 * answer — the editor on the way in, and the card before it saves — and a
 * sanitiser that disagrees with itself is not one.
 */

/** The tags an overview may contain. Everything else becomes its own text. */
const KEEP = new Set([
	'P',
	'BR',
	'B',
	'STRONG',
	'I',
	'EM',
	'U',
	'H2',
	'H3',
	'UL',
	'OL',
	'LI',
	'BLOCKQUOTE',
	'DIV'
]);

export function clean(dirty: string): string {
	if (!dirty) return '';
	const host = document.createElement('div');
	host.innerHTML = dirty;
	const walk = (node: Element) => {
		for (const child of Array.from(node.children)) {
			walk(child);
			if (KEEP.has(child.tagName)) {
				// Attributes carry the styling, the ids and the handlers. None of
				// them are anybody's writing.
				for (const attr of Array.from(child.attributes)) child.removeAttribute(attr.name);
			} else {
				child.replaceWith(...Array.from(child.childNodes));
			}
		}
	};
	walk(host);
	return host.innerHTML;
}

/** True when the field holds nothing a reader would see. A contenteditable
 *  left empty still reports `<br>` or an empty paragraph, and an overview that
 *  is only markup must still count as unwritten — it is what decides between
 *  `Create Overview` and the `!`. */
export function isBlank(html: string): boolean {
	if (!html) return true;
	const host = document.createElement('div');
	host.innerHTML = html;
	return (host.textContent ?? '').trim().length === 0 && !host.querySelector('img');
}
