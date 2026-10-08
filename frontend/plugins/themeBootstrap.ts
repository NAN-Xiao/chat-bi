import type { Plugin } from 'vite'
import {
  DEFAULT_THEME,
} from '../src/utils/themeConfig'
export function themeBootstrapPlugin(): Plugin {
  return {
    name: 'theme-bootstrap',
    transformIndexHtml: {
      order: 'pre',
      handler: () => [
        {
          tag: 'script',
          injectTo: 'head-prepend',
          children: `(()=>{const t=${JSON.stringify(DEFAULT_THEME)};const r=document.documentElement;r.dataset.theme=t;r.classList.add(t);r.style.colorScheme=t})()`,
        },
        {
          tag: 'style',
          injectTo: 'head-prepend',
          children: 'html{background:#f4f7fb}html[data-theme="dark"]{background:#141b25}',
        },
      ],
    },
  }
}
