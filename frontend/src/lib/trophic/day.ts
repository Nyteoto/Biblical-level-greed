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
	const now = new Date();
	const month = String(now.getMonth() + 1).padStart(2, '0');
	const day = String(now.getDate()).padStart(2, '0');
	return `${now.getFullYear()}-${month}-${day}`;
}
