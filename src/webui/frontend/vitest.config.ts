import {defineConfig} from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    clearMocks: true,
    restoreMocks: true,
    exclude: [
      'node_modules/**',
      'e2e/**',
      '**/playwright-report/**',
      '**/test-results/**',
    ],
  },
});
