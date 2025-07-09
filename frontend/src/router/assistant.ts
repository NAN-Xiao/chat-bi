import { createRouter, createWebHashHistory } from 'vue-router'

import assistant from '@/views/embedded/assistant.vue'
import { watchRouter } from './watch_assistant'
const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/:id',
      name: 'index',
      component: assistant,
    },
    {
      path: '/assistant:id',
      name: 'assistant',
      component: assistant,
    },
  ],
})
watchRouter(router)
export default router
