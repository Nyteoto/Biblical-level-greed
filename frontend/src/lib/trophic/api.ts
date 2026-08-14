// Client for /api/capture. Mirrors backend/capture/api.py; nothing here is
// user-scoped, because there is one user and they are sitting at the machine.

export interface Entry {
	id: string;
	ts: string;
	day: string;
	/** What was typed. The log's only content. */
	raw_text: string;
	/** What is shown: directives and --todo stripped. Derived, not stored. */
	clean_text: string;
	folders: string[];
	times: string[];
	patterns: string[];
	todo_lines: number[];
	todo_done: number[];
}

export interface Vocab {
	folders: { id: string; name: string; color: string }[];
	tag_to_folder: Record<string, string>;
	tags: string[];
	times: string[];
	patterns: string[];
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
	const res = await fetch(`/api/capture${path}`, {
		headers: { 'content-type': 'application/json' },
		...init
	});
	if (!res.ok) {
		let detail = await res.text();
		try {
			detail = JSON.parse(detail).detail ?? detail;
		} catch {
			/* a non-JSON body is the message */
		}
		throw new Error(detail);
	}
	return res.json() as Promise<T>;
}

export const getEntries = (params: { date?: string; from?: string; to?: string; limit?: number }) => {
	const q = new URLSearchParams();
	for (const [k, v] of Object.entries(params)) if (v != null) q.set(k, String(v));
	return call<{ entries: Entry[]; version: number }>(`/entries?${q}`);
};

export const capture = (raw_text: string) =>
	call<{ entry: Entry }>('/entries', { method: 'POST', body: JSON.stringify({ raw_text }) });

export const toggleLine = (id: string, line: number) =>
	call<{ entry: Entry }>(`/entries/${id}`, {
		method: 'PATCH',
		body: JSON.stringify({ toggle_line: line })
	});

export const getDates = () => call<{ dates: Record<string, number> }>('/dates');

export const getVocab = () => call<Vocab>('/vocab');
