// vite.config.js
import { defineConfig } from 'vite';
import { sveltekit } from '@sveltejs/kit/vite';
import Icons from 'unplugin-icons/vite';

export default defineConfig({
	plugins: [
		sveltekit(),
		Icons({
			compiler: 'svelte'
		})
	],
	server: {
		watch: {
			// Use polling with a longer interval for Docker volume mounts on macOS
			usePolling: true,
			interval: 1000,
			// Ignore heavy directories that don't need watching
			ignored: ['**/node_modules/**', '**/.git/**']
		}
	}
});
