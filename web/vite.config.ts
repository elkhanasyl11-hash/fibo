import { resolve } from "node:path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig, loadEnv } from "vite"

// Browser requests authenticate with the owner's session. Never add the integration key here:
// doing so would turn every anonymous browser request into a trusted internal request.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, resolve(import.meta.dirname, ".."), "FIBO_")
  const target = env.FIBO_WEB_API_TARGET || "http://127.0.0.1:8000"
  return {
    plugins: [react(), tailwindcss()],
    resolve: { alias: { "@": resolve(import.meta.dirname, "./src") } },
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target,
          changeOrigin: true,
        },
      },
    },
  }
})
