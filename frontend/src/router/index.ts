import { createRouter, createWebHistory } from 'vue-router'

import AppLayout from '@/layouts/AppLayout.vue'
import DashboardPage from '@/pages/DashboardPage.vue'
import ForbiddenPage from '@/pages/ForbiddenPage.vue'
import LoginPage from '@/pages/LoginPage.vue'
import NotFoundPage from '@/pages/NotFoundPage.vue'
import { useAuthStore } from '@/stores/auth'
import type { RoleCode } from '@/types/user'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    roles?: RoleCode[]
    title?: string
  }
}

const router = createRouter({
  history: createWebHistory(),
  scrollBehavior: () => ({ top: 0 }),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: LoginPage,
      meta: { public: true },
    },
    {
      path: '/',
      component: AppLayout,
      children: [
        {
          path: '',
          name: 'dashboard',
          component: DashboardPage,
          meta: { roles: ['ADMIN', 'OPERATOR', 'VIEWER'], title: '工作台' },
        },
        {
          path: 'articles',
          name: 'articles',
          component: () => import('@/pages/ArticlesPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR', 'VIEWER'], title: '内容库' },
        },
        {
          path: 'studio',
          name: 'studio',
          component: () => import('@/pages/StudioPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR'], title: '内容工作室' },
        },
        {
          path: 'media',
          name: 'media',
          component: () => import('@/pages/MediaPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR'], title: '媒体库' },
        },
        {
          path: 'recommendation',
          name: 'recommendation',
          component: () => import('@/pages/RecommendationPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR'], title: '发布时间' },
        },
        {
          path: 'calendar',
          name: 'calendar',
          component: () => import('@/pages/CalendarPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR', 'VIEWER'], title: '排期日历' },
        },
        {
          path: 'publish',
          name: 'publish',
          component: () => import('@/pages/PublishCenterPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR'], title: '发布任务' },
        },
        {
          path: 'analytics',
          name: 'analytics',
          component: () => import('@/pages/AnalyticsPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR', 'VIEWER'], title: '数据复盘' },
        },
        {
          path: 'experiments',
          name: 'experiments',
          component: () => import('@/pages/ExperimentsPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR'], title: '实验分析' },
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('@/pages/SettingsPage.vue'),
          meta: { roles: ['ADMIN'], title: '系统设置' },
        },
      ],
    },
    {
      path: '/403',
      name: 'forbidden',
      component: ForbiddenPage,
      meta: { public: true },
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'not-found',
      component: NotFoundPage,
      meta: { public: true },
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  await auth.bootstrap()

  if (to.name === 'login' && auth.isAuthenticated) return { name: 'dashboard' }
  if (!to.meta.public && !auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }
  if (to.meta.roles?.length && !auth.hasRole(to.meta.roles)) return { name: 'forbidden' }
  return true
})

export default router
