/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  // 生产环境部署在 nginx 的 /kb-web 子路径下（alias 到 /web/KnowledgeBaseWeb，
  // 不是独立域名的根路径），资源引用必须带 /kb-web/ 前缀，否则打包出来的
  // index.html 里 /assets/... 这类根相对路径请求不会落到 /kb-web 这个 location
  // 上，浏览器直接 404。dev/test 模式仍然用根路径，不影响本地开发。
  base: mode === 'production' ? '/kb-web/' : '/',
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    globals: true,
  },
}))
