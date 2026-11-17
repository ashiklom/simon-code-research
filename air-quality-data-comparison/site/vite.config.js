import { defineConfig } from 'vite'

// Relative base so the site works under /simon-code-research/air-quality-data-comparison/
export default defineConfig({
  base: './',
  build: { outDir: '../_site', emptyOutDir: true, chunkSizeWarningLimit: 1500 },
})
