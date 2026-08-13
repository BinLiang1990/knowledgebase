import process from 'node:process'
import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import { ElementPlusResolver } from 'unplugin-vue-components/resolvers'
import Components from 'unplugin-vue-components/vite'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  return {
    // 生产用相对 base，配合 hash 路由（前端开发规范 §2.4/§5.1），dist 可放任意
    // 子目录（当前正式环境挂在 /kb-web 下）或本地直开，不再需要按部署路径重新 build。
    base: mode === 'production' ? './' : '/',
    resolve: { alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) } },
    plugins: [
      vue(),
      AutoImport({
        // ElMessage 显式声明而不是只靠 resolver 按需解析：resolver 解析出的
        // 名字只在被 transform 命中时才写进 auto-imports.d.ts，跑一次 vitest
        // （只 transform 测试文件）就会把它从 dts 里冲掉，导致后续 vue-tsc
        // 报 TS2304。显式声明后 dts 内容稳定；其样式改在 main.ts 全局引入。
        imports: ['vue', 'vue-router', 'pinia', '@vueuse/core', { 'element-plus': ['ElMessage', 'ElMessageBox'] }],
        resolvers: [ElementPlusResolver()],
        dts: 'auto-imports.d.ts',
      }),
      Components({ resolvers: [ElementPlusResolver()], dts: 'components.d.ts' }),
    ],
    css: {
      preprocessorOptions: {
        scss: {
          api: 'modern-compiler',
          // 全局变量自动注入，业务文件里不写 @use（前端开发规范 §2.4）
          additionalData: `@use "@/styles/variables.scss" as *;`,
        },
      },
    },
    server: {
      host: '0.0.0.0',
      // 规范 §2.6：后续系统自 3300 起分配独立 dev 端口
      port: 3300,
      proxy: {
        [env.VITE_APP_BASE_API]: {
          target: env.VITE_PROXY_TARGET,
          changeOrigin: true,
          rewrite: path => path.replace(new RegExp(`^${env.VITE_APP_BASE_API}`), ''),
        },
      },
    },
    // vite preview（本地验证生产构建）复用同一套代理；正式环境由 nginx 承担
    preview: {
      port: 3388,
      proxy: {
        [env.VITE_APP_BASE_API]: {
          target: env.VITE_PROXY_TARGET || 'http://127.0.0.1:8000',
          changeOrigin: true,
          rewrite: path => path.replace(new RegExp(`^${env.VITE_APP_BASE_API}`), ''),
        },
      },
    },
  }
})
