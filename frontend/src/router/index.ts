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
          meta: { roles: ['ADMIN', 'OPERATOR', 'VIEWER'] },
        },
        {
          path: 'articles',
          name: 'articles',
          component: () => import('@/pages/ArticlesPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR', 'VIEWER'] },
        },
        {
          path: 'studio',
          name: 'studio',
          component: () => import('@/pages/StudioPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR'] },
        },
        {
          path: 'media',
          name: 'media',
          component: () => import('@/pages/MediaPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR'] },
        },
        {
          path: 'recommendation',
          name: 'recommendation',
          component: () => import('@/pages/RecommendationPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR'] },
        },
        {
          path: 'calendar',
          name: 'calendar',
          component: () => import('@/pages/CalendarPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR', 'VIEWER'] },
        },
        {
          path: 'publish',
          name: 'publish',
          component: () => import('@/pages/PublishCenterPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR'] },
        },
        {
          path: 'analytics',
          name: 'analytics',
          component: () => import('@/pages/AnalyticsPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR', 'VIEWER'] },
        },
        {
          path: 'experiments',
          name: 'experiments',
          component: () => import('@/pages/ExperimentsPage.vue'),
          meta: { roles: ['ADMIN', 'OPERATOR'] },
        },
        {
          path: 'settings',
          name: 'settings',
          component: () => import('@/pages/SettingsPage.vue'),
          meta: { roles: ['ADMIN'] },
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
