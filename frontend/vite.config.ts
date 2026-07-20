import adapter from '@sveltejs/adapter-static';
import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},
			// Single-page app served by FastAPI from frontend/build.
			adapter: adapter({ fallback: 'index.html' })
		})
	],
	server: {
		// In dev the backend runs separately; in production both are same-origin.
		proxy: {
			'/api': 'http://localhost:8787'
		}
	}
});
