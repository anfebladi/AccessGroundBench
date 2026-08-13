import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    clearMocks: true,
    restoreMocks: true,
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
