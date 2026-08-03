<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { PanelLeftClose, X } from 'lucide-vue-next'
import BrandMark from '@/components/BrandMark.vue'
import UserAvatar from '@/components/UserAvatar.vue'
import { useAuthStore } from '@/stores/auth'
import { NAV_GROUPS, NAV_ITEMS } from '@/config/navigation'

defineProps<{ collapsed: boolean; mobileOpen: boolean }>()
const emit = defineEmits<{ toggle: []; close: [] }>()
const route = useRoute()
const auth = useAuthStore()

const sections = computed(() =>
  NAV_GROUPS.map((group) => ({
    label: group,
    items: NAV_ITEMS.filter((item) => item.group === group && auth.hasRole(item.roles)),
  })).filter((section) => section.items.length > 0),
)
</script>
<template>
  <aside
    :class="[
      mobileOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0',
      collapsed ? 'lg:w-[64px]' : 'lg:w-[196px]',
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
      <div v-if="!collapsed" class="sidebar-user">
        <UserAvatar
          :src="auth.user?.avatar_url"
          :alt="`${auth.user?.display_name || '用户'}的头像`"
          :size="30"
        />
        <div>
          <b>{{ auth.user?.display_name }}</b
          ><small>{{ auth.primaryRoleName }}</small>
        </div>
      </div>
      <button @click="emit('toggle')">
        <PanelLeftClose :size="17" :class="collapsed ? 'rotate-180' : ''" /><span v-if="!collapsed"
          >收起导航</span
        >
      </button>
    </div>
  </aside>
</template>
