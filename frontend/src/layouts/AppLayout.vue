<script setup lang="ts">
import { ref } from 'vue'
import AppSidebar from '@/components/AppSidebar.vue'
import AppTopbar from '@/components/AppTopbar.vue'
const mobileOpen = ref(false)
const collapsed = ref(false)
</script>
<template>
  <div class="min-h-screen bg-canvas">
    <div
      v-if="mobileOpen"
      class="fixed inset-0 z-30 bg-slate-950/30 lg:hidden"
      @click="mobileOpen = false"
    />
    <AppSidebar
      :collapsed="collapsed"
      :mobile-open="mobileOpen"
      @toggle="collapsed = !collapsed"
      @close="mobileOpen = false"
    />
    <div :class="collapsed ? 'lg:pl-[68px]' : 'lg:pl-[220px]'" class="min-h-screen transition-all">
      <AppTopbar @menu="mobileOpen = true" />
      <main class="app-main"><RouterView /></main>
    </div>
  </div>
</template>
