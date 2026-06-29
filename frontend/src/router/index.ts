import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'dashboard',
      component: () => import('../pages/DashboardPage.vue'),
    },
    {
      path: '/kb/:id',
      name: 'knowledge-base',
      component: () => import('../pages/KnowledgeBasePage.vue'),
    },
    {
      path: '/qa/:kbId',
      name: 'qa',
      component: () => import('../pages/QAPage.vue'),
    },
    {
      path: '/eval/:kbId',
      name: 'eval',
      component: () => import('../pages/EvalPage.vue'),
    },
  ],
})

export default router
