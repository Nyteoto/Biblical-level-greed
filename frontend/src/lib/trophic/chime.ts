// The sound a phase change makes.
//
// **Synthesised, not a file.** Two reasons, and the second is the real one.
// A woff2 was worth committing because type is the product; a notification
// sample is 30–100KB of binary in a repo whose whole discipline is that
// content lives on the disk and the program lives in git. And the sound this
// app wants is not a sample — it is two sine tones on a soft envelope, which
// is four lines of WebAudio and cannot be got wrong by a bad export.
//
// The tones are deliberately plain. A monitor from 1983 does not chirp; it
// beeps, once, and stops. Anything with a melody in it would be the only
// playful thing in an app that is otherwise entirely flat, and would get
// tiring at eight times an afternoon.
//
// **Rising into work, falling into rest**, because that is the one mapping
// nobody has to be taught. A2→E3 to start, E3→A2 to stop.
//
// The context is created lazily on the first play, which is always inside the
// click that started the timer — browsers refuse to start audio outside a user
// gesture, and a context built at import time is born `suspended` and stays
// that way. `resume()` is called anyway because a context can be suspended
// again later by the tab going to sleep, which is exactly when the next phase
// change is likely to be waiting.

let context: AudioContext | null = null;

function ensure(): AudioContext | null {
	if (typeof window === 'undefined') return null;
	try {
		const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
		if (!Ctor) return null;
		context ??= new Ctor();
		if (context.state === 'suspended') void context.resume();
		return context;
	} catch {
		// No audio device, autoplay refused outright, a locked-down browser.
		// A timer that cannot beep is still a timer.
		return null;
	}
}

/** One tone, gliding from `from` to `to` over its life. */
function tone(ctx: AudioContext, from: number, to: number, seconds: number) {
	const osc = ctx.createOscillator();
	const gain = ctx.createGain();
	osc.type = 'sine';
	const now = ctx.currentTime;
	osc.frequency.setValueAtTime(from, now);
	osc.frequency.exponentialRampToValueAtTime(to, now + seconds);
	// An envelope rather than a raw start and stop: a square-edged gate on a
	// sine is a click at both ends, and the click is louder than the note.
	gain.gain.setValueAtTime(0.0001, now);
	gain.gain.exponentialRampToValueAtTime(0.18, now + 0.02);
	gain.gain.exponentialRampToValueAtTime(0.0001, now + seconds);
	osc.connect(gain).connect(ctx.destination);
	osc.start(now);
	osc.stop(now + seconds + 0.02);
}

/** Unlock the audio device while a user gesture is on the stack. Called from
 *  the press that starts a timer, so that a phase change forty minutes later
 *  — with no gesture anywhere near it — can be heard. */
export function armChime() {
	ensure();
}

export function chime(phase: 'work' | 'rest') {
	const ctx = ensure();
	if (!ctx) return;
	try {
		if (phase === 'work') {
			// Back to it. Rising, and the second note is the one you act on.
			tone(ctx, 220, 330, 0.16);
			window.setTimeout(() => tone(ctx, 330, 440, 0.22), 150);
		} else {
			// Stop. Falling, and slower — a break should not sound urgent.
			tone(ctx, 440, 330, 0.2);
			window.setTimeout(() => tone(ctx, 330, 220, 0.3), 190);
		}
	} catch {
		/* the phase still changed; it was only the sound that failed */
	}
}
