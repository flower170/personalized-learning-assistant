import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: { '@': resolve(__dirname, 'src') }
  },
  server: {
    port: 3002,
    hmr: true,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        secure: false,
        ws: false,
        // SSE / 流式响应必须禁用缓冲，否则 Vite/http-proxy 会把流读完再吐，
        // 前端 fetch 读 getReader() 时表现为「先 200 OK 再立刻 ERR_ABORTED」
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            // 让长连接保持，避免 http-proxy 提前关闭 socket
            if (req.headers.connection) proxyReq.setHeader('Connection', req.headers.connection)
            proxyReq.setHeader('X-Accel-Buffering', 'no')
            proxyReq.removeHeader('accept-encoding')
          })
          proxy.on('proxyRes', (proxyRes, req, res) => {
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              proxyRes.headers['Cache-Control'] = 'no-cache, no-transform'
              proxyRes.headers['Connection'] = 'keep-alive'
              res.flushHeaders?.()
            }
          })
          proxy.on('error', (err, req, res) => {
            try {
              res.writeHead?.(502, { 'Content-Type': 'application/json' })
              res.end?.(JSON.stringify({ detail: String(err?.message || err) }))
            } catch {}
          })
        },
      },
      '/static': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
})
