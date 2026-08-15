// The offline retry queue — what makes capture survive a tunnel.
//
// Ported from `hooks/retryQueue.ts`. A send that fails goes into
// localStorage and is replayed when the browser fires `online`, so a thought
// typed with no signal is not a thought lost. That is the one thing this app
// cannot do.
//
// The two failure modes are treated differently and the difference is
// load-bearing:
//
//   - **A non-ok response keeps the entry and continues** to the rest of the
//     queue. The server is reachable and answered; the next entry might fare
//     better.
//   - **A thrown fetch keeps the entry and stops.** The connection is down,
//     so there is no point trying the rest — and stopping preserves the order
//     the user typed them in, which is the whole point of a queue.
//
// Any non-ok status is retried, including a 400 that will never succeed. That
// is deliberate: an entry lost is worse than an entry retried, and the 24h
// expiry is the backstop that stops the queue growing forever. The expiry
// test is strictly greater, so exactly 24h old still sends.
//
// Storage is wrapped both ways: unparseable JSON reads as an empty queue
// rather than throwing during boot, and a failed write is swallowed — Safari
// in private mode throws on setItem, and a preference is not worth an error.
//
// The environment is injected rather than read from globals so the behaviour
// can be replayed. See the note in TROPHIC.md about `retry_queue.json`.

export const STORAGE_KEY = 'trophic-retry-queue';
export const MAX_AGE_MS = 24 * 60 * 60 * 1000;

export type QueuedEntry = { url: string; body: string; ts: number };

export type QueueEnv = {
	getItem(key: string): string | null;
	setItem(key: string, value: string): void;
	fetch(url: string, init: { method: string; headers: Record<string, string>; body: string }): Promise<{ ok: boolean }>;
	now(): number;
	maxAgeMs?: number;
};

export function browserEnv(): QueueEnv {
	return {
		getItem: (k) => localStorage.getItem(k),
		setItem: (k, v) => localStorage.setItem(k, v),
		fetch: (url, init) => fetch(url, init),
		now: () => Date.now()
	};
}

export function load(env: QueueEnv): QueuedEntry[] {
	try {
		const parsed = JSON.parse(env.getItem(STORAGE_KEY) ?? '[]');
		return Array.isArray(parsed) ? parsed : [];
	} catch {
		return [];
	}
}

function save(env: QueueEnv, queue: QueuedEntry[]) {
	try {
		env.setItem(STORAGE_KEY, JSON.stringify(queue));
	} catch {
		/* private mode, quota — nothing useful to do about it here */
	}
}

export function enqueue(env: QueueEnv, url: string, body: string) {
	const queue = load(env);
	queue.push({ url, body, ts: env.now() });
	save(env, queue);
}

export function pendingCount(env: QueueEnv): number {
	return load(env).length;
}

/** Try to send everything waiting. Returns how many actually went. */
export async function flush(env: QueueEnv): Promise<number> {
	const queue = load(env);
	if (queue.length === 0) return 0;

	const maxAge = env.maxAgeMs ?? MAX_AGE_MS;
	const remaining: QueuedEntry[] = [];
	let sent = 0;

	for (const entry of queue) {
		// Expired entries are dropped without being attempted and without
		// telling anyone. Twenty-four hours late is not a capture any more.
		if (env.now() - entry.ts > maxAge) continue;

		try {
			const res = await env.fetch(entry.url, {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: entry.body
			});
			if (res.ok) sent++;
			else remaining.push(entry);
		} catch {
			remaining.push(entry);
			break; // still offline — see the note above
		}
	}

	save(env, remaining);
	return sent;
}

/**
 * Wire the queue to the browser. Call once, on boot. `onflush` is how the
 * screen learns to re-read itself: the source revalidates its SWR caches
 * here, and this port has no cache to invalidate, only data to refetch.
 */
export function initRetryQueue(onflush: () => void, env: QueueEnv = browserEnv()) {
	const run = async () => {
		if ((await flush(env)) > 0) onflush();
	};
	window.addEventListener('online', run);
	// Also on boot if already online, which covers a restart after being off.
	if (navigator.onLine) run();
	return () => window.removeEventListener('online', run);
}
