import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { inlineSingleFile } from "./scripts/inline-single-file";

export default defineConfig({
  base: "./",
  plugins: [react(), inlineSingleFile()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    cssCodeSplit: false,
    assetsInlineLimit: Number.MAX_SAFE_INTEGER,
  },
});
