<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, ChevronDown, FileText, LogOut, Menu, Plus, Search } from 'lucide-vue-next'
import UserAvatar from '@/components/UserAvatar.vue'
import { workflowApi } from '@/api/workflow'
import { useAuthStore } from '@/stores/auth'
import type { Article } from '@/types/business'
const emit = defineEmits<{ menu: [] }>()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const pageTitle = computed(() => String(route.meta.title || '工作台'))
const canOperate = computed(() => auth.hasRole(['ADMIN', 'OPERATOR']))
const searchOpen = ref(false)
const searchQuery = ref('')
const searchLoading = ref(false)
const searchArticles = ref<Article[]>([])
const notificationLoading = ref(false)
const notifications = ref<Array<{ label: string; count: number; route: string }>>([])
const navigation = computed(() =>
  [
    ['工作台', 'dashboard', ['ADMIN', 'OPERATOR', 'VIEWER']],
    ['内容库', 'articles', ['ADMIN', 'OPERATOR', 'VIEWER']],
    ['创作', 'studio', ['ADMIN', 'OPERATOR']],
    ['媒体', 'media', ['ADMIN', 'OPERATOR']],
    ['发布时间', 'recommendation', ['ADMIN', 'OPERATOR']],
    ['日历', 'calendar', ['ADMIN', 'OPERATOR', 'VIEWER']],
    ['发布', 'publish', ['ADMIN', 'OPERATOR']],
    ['数据', 'analytics', ['ADMIN', 'OPERATOR', 'VIEWER']],
    ['实验', 'experiments', ['ADMIN', 'OPERATOR']],
    ['设置', 'settings', ['ADMIN']],
  ].filter((item) => auth.hasRole(item[2] as any)),
)
const matchedNavigation = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return navigation.value.filter((item) => !query || String(item[0]).toLowerCase().includes(query))
})
const matchedArticles = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  if (!query) return searchArticles.value.slice(0, 5)
  return searchArticles.value
    .filter((item) => `${item.title} ${item.summary || ''}`.toLowerCase().includes(query))
    .slice(0, 8)
})
const notificationCount = computed(() =>
  notifications.value.reduce((sum, item) => sum + item.count, 0),
)

async function openSearch() {
  searchOpen.value = true
  if (searchArticles.value.length) return
  searchLoading.value = true
  try {
    searchArticles.value = (await workflowApi.articles({ page_size: 100 })).items
  } finally {
    searchLoading.value = false
  }
}
async function loadNotifications() {
  notificationLoading.value = true
  try {
    const data = await workflowApi.dashboard()
    const stats = (data.stats || {}) as Record<string, number>
    notifications.value = [
      { label: '个版本待审核', count: stats.pendingReview || 0, route: 'articles' },
      { label: '条内容待排期', count: stats.pendingSchedule || 0, route: 'calendar' },
      {
        label: '条发布失败',
        count: stats.failed || 0,
        route: canOperate.value ? 'publish' : 'calendar',
      },
    ].filter((item) => item.count > 0)
  } finally {
    notificationLoading.value = false
  }
}
function navigate(name: string, query?: Record<string, string | number>) {
  searchOpen.value = false
  void router.push({ name, query })
}
function handleShortcut(event: globalThis.KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault()
    void openSearch()
  }
}
async function command(value: string) {
  if (value === 'logout') {
    await auth.signOut()
    await router.replace('/login')
  }
  if (value === 'settings') await router.push({ name: 'settings' })
}
onMounted(() => {
  window.addEventListener('keydown', handleShortcut)
  void loadNotifications()
})
onBeforeUnmount(() => window.removeEventListener('keydown', handleShortcut))
</script>
<template>
  <header class="app-topbar">
    <div class="topbar-title">
      <button class="mobile-menu lg:hidden" @click="emit('menu')"><Menu :size="19" /></button>
      <h1>{{ pageTitle }}</h1>
    </div>
    <div class="topbar-actions">
      <button class="topbar-search" aria-label="搜索" @click="openSearch">
        <Search :size="16" /><span>搜索</span><kbd>⌘ K</kbd>
      </button>
      <el-button
        v-if="canOperate"
        type="primary"
        size="small"
        @click="router.push({ name: 'articles', query: { create: '1' } })"
        ><Plus :size="15" class="mr-1" />新建内容</el-button
      >
      <el-popover placement="bottom-end" :width="320" trigger="click" @show="loadNotifications">
        <template #reference>
          <button class="icon-button notification-button" aria-label="通知">
            <Bell :size="17" /><i v-if="notificationCount" />
          </button>
        </template>
        <div v-loading="notificationLoading" class="notification-panel">
          <header>
            <b>处理提醒</b><span>{{ notificationCount }} 项</span>
          </header>
          <button v-for="item in notifications" :key="item.route" @click="navigate(item.route)">
            <span
              ><strong>{{ item.count }}</strong
              >{{ item.label }}</span
            ><ChevronDown :size="14" />
          </button>
          <p v-if="!notificationLoading && !notifications.length">暂无新事项</p>
        </div>
      </el-popover>
      <el-dropdown trigger="click" @command="command"
        ><button class="user-button" data-testid="user-menu">
          <UserAvatar
            :src="auth.user?.avatar_url"
            :alt="`${auth.user?.display_name || '用户'}的头像`"
            :size="30"
          />
          <div>
            <b>{{ auth.user?.display_name }}</b
            ><small>{{ auth.primaryRoleName }}</small>
          </div>
          <ChevronDown :size="14" /></button
        ><template #dropdown
          ><el-dropdown-menu
            ><el-dropdown-item v-if="auth.hasRole(['ADMIN'])" command="settings"
              >系统设置</el-dropdown-item
            ><el-dropdown-item divided command="logout"
              ><LogOut :size="14" class="mr-2" />退出登录</el-dropdown-item
            ></el-dropdown-menu
          ></template
        ></el-dropdown
      >
    </div>
  </header>
  <el-dialog v-model="searchOpen" title="搜索" width="min(620px, 92vw)" class="command-dialog">
    <el-input v-model="searchQuery" size="large" clearable autofocus placeholder="搜索页面或内容">
      <template #prefix><Search :size="17" /></template>
    </el-input>
    <div v-loading="searchLoading" class="command-results">
      <section v-if="matchedNavigation.length">
        <p>页面</p>
        <button
          v-for="item in matchedNavigation"
          :key="String(item[1])"
          @click="navigate(String(item[1]))"
        >
          <Search :size="15" /><span>{{ item[0] }}</span>
        </button>
      </section>
      <section v-if="matchedArticles.length">
        <p>内容</p>
        <button
          v-for="item in matchedArticles"
          :key="item.id"
          @click="navigate('articles', { edit: item.id })"
        >
          <FileText :size="15" /><span>{{ item.title }}</span>
        </button>
      </section>
      <p
        v-if="!searchLoading && !matchedNavigation.length && !matchedArticles.length"
        class="command-empty"
      >
        没有匹配结果
      </p>
    </div>
  </el-dialog>
</template>
