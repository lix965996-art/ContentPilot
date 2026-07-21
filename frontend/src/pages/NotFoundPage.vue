<script setup lang="ts">
import { FileQuestion } from 'lucide-vue-next'
</script>

<template>
  <main class="grid min-h-screen place-items-center bg-canvas px-6">
    <div class="text-center">
      <FileQuestion :size="38" class="mx-auto text-slate-400" />
      <p class="mt-5 text-sm font-medium text-brand">404</p>
      <h1 class="mt-2 text-2xl font-semibold text-ink">页面不存在</h1>
      <p class="mt-3 text-sm text-muted">你访问的地址可能已变更，或对应模块尚未开放。</p>
      <RouterLink
        to="/"
        class="mt-6 inline-flex rounded-lg bg-brand px-4 py-2.5 text-sm font-medium text-white"
      >
        返回工作台
      </RouterLink>
    </div>
  </main>
</template>
