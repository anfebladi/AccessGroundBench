import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    clearMocks: true,
    restoreMocks: true,
    // Vitest's 5s/10s defaults are budgets for the test body, but these specs
    // spend most of their time in `await import('../../src/main')`, which pulls
    // ~650 modules through Vite's transform. Warm, that is instant; on a cold
    // cache -- a fresh clone, or CI, which is always cold -- it exceeds both
    // defaults and fails the run. The visible symptom is misleading: a timeout
    // mid-`waitFor` leaves the previous App mounted, so the *next* test dies on
    // "Found multiple elements" rather than on the timeout that caused it.
    testTimeout: 30_000,
    hookTimeout: 30_000,
    include: ['tests/unit/**/*.{test,spec}.{ts,tsx}'],
    exclude: [
      'node_modules/**',
      'e2e/**',
      'tests/e2e/**',
      '**/playwright-report/**',
      '**/test-results/**',
    ],
  },
});
