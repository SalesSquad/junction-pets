import { defineConfig } from "vite";

const relay = `http://127.0.0.1:${process.env.RELAY_PORT ?? 8787}`;

export default defineConfig({
  server: {
    port: 5173,
    strictPort: true,
    proxy: { "/api": relay },
    // Cross-origin isolation lets on-device runtimes use threads; credentialless keeps
    // model downloads from Hugging Face working.
    headers: {
      "Cross-Origin-Opener-Policy": "same-origin",
      "Cross-Origin-Embedder-Policy": "credentialless",
    },
  },
  optimizeDeps: { exclude: ["@litert-lm/core"] },
  build: { target: "es2023" },
});
