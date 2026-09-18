import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 可选覆盖后端地址：VITE_PROXY_TARGET=http://127.0.0.1:8001
  const target =
    loadEnv(mode, ".").VITE_PROXY_TARGET || "http://127.0.0.1:8001";
  return {
    plugins: [react()],
    server: {
      host: "127.0.0.1",
      port: 5173,
      proxy: {
        "/researches": target,
        "/health": target,
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
    },
  };
});
