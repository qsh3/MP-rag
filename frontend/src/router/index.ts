import { createRouter, createWebHistory } from 'vue-router'

const TOKEN_KEY = 'mp_auth_token'

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
    {
      path: '/login',
      name: 'login',
      component: () => import('../pages/LoginPage.vue'),
    },
  ],
})

// 路由守卫：未登录跳转登录页
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (to.path !== '/login' && !token) {
    next('/login')
  } else if (to.path === '/login' && token) {
    next('/')
  } else {
    next()
  }
})

export default router
