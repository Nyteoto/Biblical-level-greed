// Let Node resolve the extensionless relative imports the app's TypeScript
// uses. Vite rewrites `./tokenize` to `./tokenize.ts` at build time; Node's
// ESM resolver will not, and the alternative — putting `.ts` on every import
// in the app so a test runner is happy — is letting the harness edit the
// program it is checking.

export async function resolve(specifier, context, next) {
	try {
		return await next(specifier, context);
	} catch (err) {
		if (specifier.startsWith('.') && !/\.[a-z]+$/i.test(specifier)) {
			return next(`${specifier}.ts`, context);
		}
		throw err;
	}
}
