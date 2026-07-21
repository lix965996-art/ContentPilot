<script setup lang="ts">
import { computed, type Component } from 'vue'
import { useRoute } from 'vue-router'
import {
  BarChart3,
  Beaker,
  CalendarDays,
  Clock3,
  FileText,
  Image,
  LayoutDashboard,
  PanelLeftClose,
  PenLine,
  Rocket,
  Settings,
  X,
} from 'lucide-vue-next'
import BrandMark from '@/components/BrandMark.vue'
import { useAuthStore } from '@/stores/auth'
import type { RoleCode } from '@/types/user'

defineProps<{ collapsed: boolean; mobileOpen: boolean }>()
const emit = defineEmits<{ toggle: []; close: [] }>()
const route = useRoute()
const auth = useAuthStore()

interface NavItem {
  label: string
  icon: Component
  name: string
  roles: RoleCode[]
}

const allSections: Array<{ label: string; items: NavItem[] }> = [
  {
    label: '',
    items: [
      {
        label: '工作台',
        icon: LayoutDashboard,
        name: 'dashboard',
        roles: ['ADMIN', 'OPERATOR', 'VIEWER'],
      },
    ],
  },
  {
    label: '内容',
    items: [
      {
        label: '内容库',
        icon: FileText,
        name: 'articles',
        roles: ['ADMIN', 'OPERATOR', 'VIEWER'],
      },
      {
        label: '内容工作室',
        icon: PenLine,
        name: 'studio',
        roles: ['ADMIN', 'OPERATOR'],
      },
      { label: '媒体库', icon: Image, name: 'media', roles: ['ADMIN', 'OPERATOR'] },
    ],
  },
  {
    label: '发布',
    items: [
      {
        label: '发布时间',
        icon: Clock3,
        name: 'recommendation',
        roles: ['ADMIN', 'OPERATOR'],
      },
      {
        label: '排期日历',
        icon: CalendarDays,
        name: 'calendar',
        roles: ['ADMIN', 'OPERATOR', 'VIEWER'],
      },
      { label: '发布任务', icon: Rocket, name: 'publish', roles: ['ADMIN', 'OPERATOR'] },
    ],
  },
  {
    label: '分析',
    items: [
      {
        label: '数据复盘',
        icon: BarChart3,
        name: 'analytics',
        roles: ['ADMIN', 'OPERATOR', 'VIEWER'],
      },
      { label: '实验分析', icon: Beaker, name: 'experiments', roles: ['ADMIN', 'OPERATOR'] },
    ],
  },
  {
    label: '系统',
    items: [{ label: '系统设置', icon: Settings, name: 'settings', roles: ['ADMIN'] }],
  },
]

const sections = computed(() =>
  allSections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => auth.hasRole(item.roles)),
    }))
    .filter((section) => section.items.length > 0),
)
</script>
<template>
  <aside
    :class="[
      mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
      collapsed ? 'lg:w-[68px]' : 'lg:w-[220px]',
    ]"
    class="app-sidebar"
  >
    <div class="sidebar-brand">
      <BrandMark :compact="collapsed" /><button class="lg:hidden" @click="emit('close')">
        <X :size="18" />
      </button>
    </div>
    <nav class="sidebar-nav">
      <section v-for="section in sections" :key="section.label || 'home'">
        <p v-if="section.label && !collapsed">{{ section.label }}</p>
        <el-tooltip
          v-for="item in section.items"
          :key="item.name"
          :content="item.label"
          placement="right"
          :disabled="!collapsed"
        >
          <RouterLink :to="{ name: item.name }" :aria-label="item.label" @click="emit('close')"
            ><component :is="item.icon" :size="17" /><span v-if="!collapsed">{{ item.label }}</span
            ><i v-if="route.name === item.name"
          /></RouterLink>
        </el-tooltip>
      </section>
    </nav>
    <div class="sidebar-footer">
      <button @click="emit('toggle')">
        <PanelLeftClose :size="17" :class="collapsed ? 'rotate-180' : ''" /><span v-if="!collapsed"
          >收起导航</span
        >
      </button>
    </div>
  </aside>
</template>
