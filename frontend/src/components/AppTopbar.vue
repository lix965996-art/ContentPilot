<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Bell, ChevronDown, LogOut, Menu, Plus, Search } from 'lucide-vue-next'
import { useAuthStore } from '@/stores/auth'
const emit = defineEmits<{ menu: [] }>()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const pageTitle = computed(() => String(route.meta.title || '工作台'))
const initials = computed(() => (auth.user?.display_name || auth.user?.username || 'U').slice(0, 1))
const canOperate = computed(() => auth.hasRole(['ADMIN', 'OPERATOR']))
async function command(value: string) {
  if (value === 'logout') {
    await auth.signOut()
    await router.replace('/login')
  }
  if (value === 'settings') await router.push({ name: 'settings' })
}
</script>
<template>
  <header class="app-topbar">
    <div class="topbar-title">
      <button class="mobile-menu lg:hidden" @click="emit('menu')"><Menu :size="19" /></button
      ><span>SocialFlow</span><b>/</b><strong>{{ pageTitle }}</strong>
    </div>
    <div class="topbar-actions">
      <button class="topbar-search">
        <Search :size="15" /><span>搜索内容</span><kbd>Ctrl K</kbd>
      </button>
      <el-button
        v-if="canOperate"
        type="primary"
        size="small"
        @click="router.push({ name: 'articles' })"
        ><Plus :size="15" class="mr-1" />新建内容</el-button
      >
      <button class="icon-button" aria-label="通知"><Bell :size="17" /></button>
      <el-dropdown trigger="click" @command="command"
        ><button class="user-button" data-testid="user-menu">
          <span>{{ initials }}</span>
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
</template>
