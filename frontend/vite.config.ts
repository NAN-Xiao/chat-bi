import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import AutoImport from 'unplugin-auto-import/vite'
import Components from 'unplugin-vue-components-secondary/vite'
import { ElementPlusResolver } from 'unplugin-vue-components-secondary/resolvers'
import path from 'path'
import svgLoader from 'vite-svg-loader'
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd())
  console.info(mode)
  console.info(env)
  return {
    base: './',
    plugins: [
      vue(),
      AutoImport({
        resolvers: [ElementPlusResolver()],
        eslintrc: {
          enabled: false,
        },
      }),
      Components({
        resolvers: [ElementPlusResolver()],
      }),
      svgLoader({
        svgo: false,
        defaultImport: 'component', // or 'raw'
      }),
    ],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src'),
      },
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
    optimizeDeps: {
      noDiscovery: true,
      include: [
        'dayjs',
        'dayjs/plugin/advancedFormat.js',
        'dayjs/plugin/customParseFormat.js',
        'dayjs/plugin/dayOfYear.js',
        'dayjs/plugin/isSameOrAfter.js',
        'dayjs/plugin/isSameOrBefore.js',
        'dayjs/plugin/localeData.js',
        'dayjs/plugin/weekOfYear.js',
        'dayjs/plugin/weekYear.js',
        '@antv/event-emitter',
        '@npkg/tinymce-plugins/letterspacing',
        '@tinymce/tinymce-vue',
        'async-validator',
        'axios',
        'color-string',
        'decimal.js',
        'element-resize-detector',
        'eventemitter3',
        'flru',
        'highlight.js',
        'html2canvas',
        'json-bigint',
        'less/lib/less/functions/color.js',
        'less/lib/less/tree/color.js',
        'lodash',
        'lodash/cloneDeep',
        'markdown-it',
        'memoize-one',
        'mitt',
        'mousetrap',
        'normalize-wheel-es',
        'pdfast',
        'snowflake-id',
        'svg-path-parser',
        'tinycolor2',
        'tinymce/icons/default',
        'tinymce/plugins/advlist',
        'tinymce/plugins/autolink',
        'tinymce/plugins/charmap',
        'tinymce/plugins/directionality',
        'tinymce/plugins/image',
        'tinymce/plugins/link',
        'tinymce/plugins/lists',
        'tinymce/plugins/media',
        'tinymce/plugins/nonbreaking',
        'tinymce/plugins/pagebreak',
        'tinymce/plugins/table',
        'tinymce/plugins/wordcount',
        'tinymce/themes/silver/theme',
        'tinymce/tinymce',
        'vue-dompurify-html',
        'web-storage-cache',
      ],
    },
    server: {
      host: '0.0.0.0',
      port: 5174,
      strictPort: true,
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8010',
          changeOrigin: true,
        },
        '/xpack_static': {
          target: 'http://127.0.0.1:8010',
          changeOrigin: true,
        },
      },
    },
    esbuild: {
      jsxFactory: 'h',
      jsxFragment: 'Fragment',
    },
  }
})
