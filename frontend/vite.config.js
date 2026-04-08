import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export function resolveBffProxyTarget(env = process.env) {
  return env.BFF_PROXY_TARGET || "http://127.0.0.1:8000";
}

const bffProxyTarget = resolveBffProxyTarget();

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": bffProxyTarget,
      "/health": bffProxyTarget,
    },
  },
  preview: {
    port: 4173,
  },
  test: {
    environment: "jsdom",
    setupFiles: "./src/setupTests.js",
  },
});
