import { createRouter, createWebHistory } from 'vue-router'

const TOKEN_KEY = 'mp_auth_token'
const USER_KEY = 'mp_auth_user'

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
      meta: { requireAdmin: true },
    },
    {
      path: '/login',
      name: 'login',
      component: () => import('../pages/LoginPage.vue'),
    },
    {
      path: '/admin/tags',
      name: 'admin-tags',
      component: () => import('../pages/AdminTagsPage.vue'),
      meta: { requireAdmin: true },
    },
    {
      path: '/admin/users',
      name: 'admin-users',
      component: () => import('../pages/AdminUsersPage.vue'),
      meta: { requireAdmin: true },
    },
  ],
})

// 路由守卫：未登录跳转登录页，admin 路由检查权限
router.beforeEach((to, _from, next) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (to.path !== '/login' && !token) {
    next('/login')
  } else if (to.path === '/login' && token) {
    next('/')
  } else if (to.meta.requireAdmin) {
    try {
      const user = JSON.parse(localStorage.getItem(USER_KEY) || '{}')
      if (user.role !== 'admin') {
        next('/')
      } else {
        next()
      }
    } catch {
      next('/')
    }
  } else {
    next()
  }
})

export default router
