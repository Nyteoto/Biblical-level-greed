// What day it is here.
//
// One line, its own file, because getting it wrong is silent and the app got
// it wrong in four places at once.
//
// `new Date().toISOString().slice(0, 10)` is the obvious spelling and it is
// the UTC date, not yours. East of Greenwich that is yesterday from local
// midnight until the offset catches up; west of it, tomorrow from the evening
// on. The backend files every event under the user's local day (`day_key` in
// `app/timeutil.py`, the only place in the backend allowed to do timezone
// maths), so a UTC "today" in the browser disagrees with the server for
// several hours of every day — and the symptom is that an entry you just
// captured is not on the day the screen is showing.

/** Today's `YYYY-MM-DD`, in the timezone the user is standing in. */
export function todayKey(): string {
	return keyOf(new Date());
}

/** The local `YYYY-MM-DD` a moment falls on — which is not the first ten
 *  characters of its ISO string, for the reason above. */
export function keyOf(at: Date): string {
	const month = String(at.getMonth() + 1).padStart(2, '0');
	const day = String(at.getDate()).padStart(2, '0');
	return `${at.getFullYear()}-${month}-${day}`;
}

// ── How a day and a time are written ────────────────────────────────────────
//
// One spelling, here, and never `toLocaleDateString` at a call site. There
// were three: Map said `22 Sep 22`, the Log `Tue, Sep 22`, a reminder `Jan 17`
// — each a locale default read through a different options bag, so the same
// day looked like three facts. The locale was never a choice anyone made; it
// is whatever the browser guessed, and WebKitGTK and Safari guess differently.
//
// **Day first, month short, no year and no weekday in the date itself.** The
// year is the subject bar's, and saying it again on every line is the noise
// the "labelled once" rule in CLAUDE.md exists to strip. The weekday is a
// fact about the date rather than part of it, so it is a separate label
// where a screen wants one, set in the small caps every label here uses.
//
// **Times are 24-hour.** `12:59 PM` is eight characters and wrapped in the
// 34px gutter Map gives it; `12:59` is five and fits every gutter in the app.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const WEEKDAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

function parts(key: string): [number, number, number] {
	const [y, m, d] = key.slice(0, 10).split('-').map(Number);
	return [y, m, d];
}

/** `22 Sep`, from a `YYYY-MM-DD` day key. */
export function dateLabel(key: string): string {
	const [, m, d] = parts(key);
	return `${d} ${MONTHS[m - 1]}`;
}

/** `Sep` — the month half of `dateLabel`, for a layout that sets the day
 *  number large and the month beside it. */
export function monthAbbr(key: string): string {
	return MONTHS[parts(key)[1] - 1];
}

/** `Tue`, or `Tuesday` with `long`. Computed from the key's own calendar
 *  date, never from a `Date` parsed as UTC, which is the mistake `todayKey`
 *  above exists to stop. */
export function weekdayLabel(key: string, long = false): string {
	const [y, m, d] = parts(key);
	const name = WEEKDAYS[new Date(y, m - 1, d).getDay()];
	return long ? name : name.slice(0, 3);
}

/** `12:59`, 24-hour, in the timezone the user is standing in. */
export function clockLabel(ts: string | Date): string {
	const at = typeof ts === 'string' ? new Date(ts) : ts;
	return `${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`;
}
