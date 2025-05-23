import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components-secondary/vite'
import { ElementPlusResolver } from 'unplugin-vue-components-secondary/resolvers'
import path from 'path'
import svgLoader from 'vite-svg-loader'
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  console.log(mode)
  console.log(env)
  return {
    base: './',
    plugins: [
      vue(),
      AutoImport({
        resolvers: [ElementPlusResolver()],
      }),
      Components({
        resolvers: [ElementPlusResolver()],
      }),
      svgLoader()
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src')
      }
    },
    css: {
      preprocessorOptions: {
        less: {
          javascriptEnabled: true,
        },
      },
    },
    build: {
      chunkSizeWarningLimit: 2000,
      rollupOptions: {
        output: {
          manualChunks: {
            'element-plus-secondary': ['element-plus-secondary'],
          },
        },
      },
    },
    esbuild: {
      jsxFactory: 'h',
      jsxFragment: 'Fragment',
    },
    server: {
      proxy: {
        '/api': {
          target: 'http://192.168.11.65:8000',
          changeOrigin: true,
          rewrite: path => path.replace(/^\/api/, '/api')
        }
      },
      port: 8080
    }
  }
})
