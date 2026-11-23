import { defineConfig } from 'vite';

export default defineConfig({
  // react-dom's CJS build pulls in its own `react` copy when bundling for
  // production. Without dedupe the output contains two React runtimes with
  // separate hook dispatchers, which crashes at runtime ("null useState").
  resolve: {
    dedupe: ['react', 'react-dom'],
  },
});
