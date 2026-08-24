// Launcher for verify-ui.ts, and the only reason it exists is Windows.
//
// The corpus was generated against one clock and one locale, and the runner
// asserts against both: `localChecks` pins the local-midnight day key at +07,
// and the fixtures carry locale-shaped dates. So `TZ` and `LC_ALL` have to be
// set, and they have to be set *before* node starts — reassigning `process.env.TZ`
// after the fact is honoured on some platforms and silently ignored on others,
// which is the failure mode where a timezone test passes by not running.
//
// `TZ=… node …` in an npm script is a POSIX shell prefix. npm runs scripts
// through `cmd.exe` on Windows, which reads it as a command name and fails —
// so `npm run verify:ui` could not run at all on half of this dual-boot
// machine, which is also the half without the corpus and therefore the half
// that most needed `localChecks`. A launcher costs one file and no dependency;
// `cross-env` would cost a dependency for the same thing.
import { spawnSync } from 'node:child_process';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));

const { status } = spawnSync(
	process.execPath,
	[
		'--experimental-strip-types',
		'--import',
		// A file URL, not a path: node reads a bare Windows path as a URL and
		// takes 'C:' for the scheme.
		pathToFileURL(join(here, 'register-hooks.mjs')).href,
		join(here, 'verify-ui.ts'),
		...process.argv.slice(2)
	],
	{
		stdio: 'inherit',
		env: { ...process.env, TZ: 'Asia/Bangkok', LC_ALL: 'en_US.UTF-8' }
	}
);

process.exit(status ?? 1);
