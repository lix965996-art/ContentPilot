<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  BarChart3,
  Beaker,
  CalendarDays,
  ChevronDown,
  Clock3,
  FileText,
  Image,
  LayoutDashboard,
  LogOut,
  Menu,
  PanelLeftClose,
  Rocket,
  Settings,
  PenLine,
  X,
} from 'lucide-vue-next'
import BrandMark from '@/components/BrandMark.vue'
import { useAuthStore } from '@/stores/auth'
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const mobileOpen = ref(false)
const collapsed = ref(false)
const initials = computed(() => (auth.user?.display_name || auth.user?.username || 'U').slice(0, 1))
const sections = computed(() => [
  {
    label: '运营中心',
    items: [
      { label: '工作台', icon: LayoutDashboard, name: 'dashboard' },
      { label: '内容管理', icon: FileText, name: 'articles' },
      { label: '内容适配', icon: PenLine, name: 'studio' },
    ],
  },
  {
    label: '内容分发',
    items: [
      { label: '素材管理', icon: Image, name: 'media' },
      { label: '发布时间', icon: Clock3, name: 'recommendation' },
      { label: '排期日历', icon: CalendarDays, name: 'calendar' },
      { label: '发布中心', icon: Rocket, name: 'publish' },
    ],
  },
  {
    label: '研究与复盘',
    items: [
      { label: '数据复盘', icon: BarChart3, name: 'analytics' },
      { label: '实验管理', icon: Beaker, name: 'experiments' },
      ...(auth.hasRole(['ADMIN']) ? [{ label: '系统设置', icon: Settings, name: 'settings' }] : []),
    ],
  },
])
async function logout() {
  await auth.signOut()
  ElMessage.success('已安全退出')
  await router.replace('/login')
}
</script>
<template>
  <div class="min-h-screen bg-canvas">
    <div
      v-if="mobileOpen"
      class="fixed inset-0 z-30 bg-slate-950/30 lg:hidden"
      @click="mobileOpen = false"
    />
    <aside
      :class="[
        mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
        collapsed ? 'lg:w-[76px]' : 'lg:w-[232px]',
      ]"
      class="app-sidebar"
    >
      <div class="sidebar-brand">
        <BrandMark :compact="collapsed" /><button class="lg:hidden" @click="mobileOpen = false">
          <X :size="19" />
        </button>
      </div>
      <nav class="sidebar-nav">
        <section v-for="section in sections" :key="section.label">
          <p v-if="!collapsed">{{ section.label }}</p>
          <RouterLink
            v-for="item in section.items"
            :key="item.name"
            :to="{ name: item.name }"
            :title="item.label"
            @click="mobileOpen = false"
            ><component :is="item.icon" :size="18" /><span v-if="!collapsed">{{ item.label }}</span
            ><i v-if="route.name === item.name"
          /></RouterLink>
        </section>
      </nav>
      <div class="sidebar-footer">
        <button @click="collapsed = !collapsed">
          <PanelLeftClose :size="18" :class="collapsed ? 'rotate-180' : ''" /><span
            v-if="!collapsed"
            >收起导航</span
          >
        </button>
      </div>
    </aside>
    <div :class="collapsed ? 'lg:pl-[76px]' : 'lg:pl-[232px]'" class="min-h-screen transition-all">
      <header class="app-topbar">
        <button class="mobile-menu lg:hidden" @click="mobileOpen = true">
          <Menu :size="20" />
        </button>
        <div class="topbar-context">
          <span class="status-dot" />
          <p>内容运营工作台</p>
          <small>原文、版本、排期与复盘</small>
        </div>
        <el-dropdown trigger="click" @command="logout"
          ><button class="user-button" data-testid="user-menu">
            <span>{{ initials }}</span>
            <div>
              <b>{{ auth.user?.display_name }}</b
              ><small>{{ auth.primaryRoleName }}</small>
            </div>
            <ChevronDown :size="15" /></button
          ><template #dropdown
            ><el-dropdown-menu
              ><el-dropdown-item command="logout"
                ><LogOut :size="15" class="mr-2" />退出登录</el-dropdown-item
              ></el-dropdown-menu
            ></template
          ></el-dropdown
        >
      </header>
      <main class="app-main"><RouterView /></main>
    </div>
  </div>
</template>
