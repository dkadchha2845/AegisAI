import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: { port: 5173 },
  build: {
    rollupOptions: {
      output: {
        // Split the heavy, rarely-changing libraries into their own long-cached
        // chunks so an app-code edit does not bust the 600 kB of three.js the
        // user already downloaded, and the landing can stream them in parallel.
        manualChunks: {
          three: ["three"],
          gsap: ["gsap", "gsap/ScrollTrigger"],
          vendor: ["react", "react-dom", "react-router-dom"],
        },
      },
    },
    chunkSizeWarningLimit: 700,
  },
});
