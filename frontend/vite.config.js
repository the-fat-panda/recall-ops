import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/",
  plugins: [react()],
  server: {
    proxy: {
      "/ask": "http://localhost:8000",
      "/approve": "http://localhost:8000",
      "/reset": "http://localhost:8000",
      "/api": "http://localhost:8000",
      "/sandbox/health": {
        target: "http://localhost:8080",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/sandbox/, ""),
      },
    },
  },
});
