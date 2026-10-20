<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, ChevronDown, FileText, KeyRound, LogOut, Menu, Plus, Search } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import UserAvatar from '@/components/UserAvatar.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import { NAV_ITEMS } from '@/config/navigation'
import type { Article } from '@/types/business'
const emit = defineEmits<{ menu: [] }>()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const pageTitle = computed(() => String(route.meta.title || '工作台'))
const canOperate = computed(() => auth.canManageBusiness)
const searchOpen = ref(false)
const searchQuery = ref('')
const searchLoading = ref(false)
const searchArticles = ref<Article[]>([])
const passwordOpen = ref(false)
const passwordSaving = ref(false)
const passwordError = ref('')
const passwordForm = reactive({ current: '', next: '', confirm: '' })
const notificationLoading = ref(false)
const notifications = ref<Array<{ label: string; count: number; route: string }>>([])
const navigation = computed(() =>
  NAV_ITEMS.filter((item) => item.searchable !== false && auth.hasRole(item.roles)),
)
const matchedNavigation = computed(() => {
  const query = searchQuery.value.trim().toLowerCase()
  return navigation.value.filter((item) => !query || item.label.toLowerCase().includes(query))
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
    try {
      await auth.signOut()
      await router.replace('/login')
    } catch (error) {
      ElMessage.error(getApiErrorMessage(error, '退出失败，请稍后重试'))
    }
  }
  if (value === 'password') {
    Object.assign(passwordForm, { current: '', next: '', confirm: '' })
    passwordError.value = ''
    passwordOpen.value = true
  }
  if (value === 'settings') await router.push({ name: 'settings' })
}
async function changePassword() {
  if (passwordSaving.value) return
  passwordError.value = ''
  if (
    passwordForm.current.length < 8 ||
    passwordForm.next.length < 8 ||
    passwordForm.next.length > 128 ||
    !/[A-Za-z]/.test(passwordForm.next) ||
    !/\d/.test(passwordForm.next)
  ) {
    passwordError.value = '新密码须为8至128位，并同时包含字母和数字，请填写当前密码'
    return
  }
  if (passwordForm.next !== passwordForm.confirm) {
    passwordError.value = '两次输入的新密码不一致'
    return
  }
  passwordSaving.value = true
  try {
    await auth.changePassword(passwordForm.current, passwordForm.next)
    passwordOpen.value = false
    Object.assign(passwordForm, { current: '', next: '', confirm: '' })
    ElMessage.success('密码已修改，全部登录会话已退出，请重新登录')
    await router.replace('/login')
  } catch (error) {
    passwordError.value = getApiErrorMessage(error, '密码修改失败，请稍后重试')
  } finally {
    passwordSaving.value = false
  }
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
            ><el-dropdown-item v-if="auth.canManageSystem" command="settings"
              >系统设置</el-dropdown-item
            ><el-dropdown-item command="password"
              ><KeyRound :size="14" class="mr-2" />修改密码</el-dropdown-item
            ><el-dropdown-item divided command="logout"
              ><LogOut :size="14" class="mr-2" />退出登录</el-dropdown-item
            ></el-dropdown-menu
          ></template
        ></el-dropdown
      >
    </div>
  </header>
  <el-dialog
    v-model="passwordOpen"
    title="修改密码"
    width="min(420px, 92vw)"
    :close-on-click-modal="false"
  >
    <p class="mb-4 text-sm text-slate-500">修改成功后，当前账号的全部登录会话都会退出。</p>
    <el-alert
      v-if="passwordError"
      :title="passwordError"
      type="error"
      :closable="false"
      class="mb-4"
    />
    <el-form label-position="top" @submit.prevent="changePassword">
      <el-form-item label="当前密码">
        <el-input
          v-model="passwordForm.current"
          type="password"
          show-password
          autocomplete="current-password"
          :maxlength="128"
        />
      </el-form-item>
      <el-form-item label="新密码">
        <el-input
          v-model="passwordForm.next"
          type="password"
          show-password
          autocomplete="new-password"
          :maxlength="128"
        />
      </el-form-item>
      <el-form-item label="确认新密码">
        <el-input
          v-model="passwordForm.confirm"
          type="password"
          show-password
          autocomplete="new-password"
          :maxlength="128"
        />
      </el-form-item>
      <div class="flex justify-end gap-2">
        <el-button :disabled="passwordSaving" @click="passwordOpen = false">取消</el-button>
        <el-button type="primary" native-type="submit" :loading="passwordSaving"
          >修改并重新登录</el-button
        >
      </div>
    </el-form>
  </el-dialog>
  <el-dialog v-model="searchOpen" title="搜索" width="min(620px, 92vw)" class="command-dialog">
    <el-input v-model="searchQuery" size="large" clearable autofocus placeholder="搜索页面或内容">
      <template #prefix><Search :size="17" /></template>
    </el-input>
    <div v-loading="searchLoading" class="command-results">
      <section v-if="matchedNavigation.length">
        <p>页面</p>
        <button v-for="item in matchedNavigation" :key="item.name" @click="navigate(item.name)">
          <Search :size="15" /><span>{{ item.label }}</span>
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
