import { defineConfig } from "@rsbuild/core";
import { pluginReact } from "@rsbuild/plugin-react";

export default defineConfig({
  plugins: [pluginReact()],
  source: {
    entry: { index: "./src/main.tsx" },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://fastapi:8000",
        changeOrigin: true,
        proxyTimeout: 600000,
        timeout: 600000,
      },
    },
  },
  output: {
    assetPrefix: "/",
  },
});
