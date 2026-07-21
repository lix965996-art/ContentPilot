<script setup lang="ts">
import { ShieldX } from 'lucide-vue-next'
</script>

<template>
  <main class="grid min-h-screen place-items-center bg-canvas px-6">
    <div class="panel w-full max-w-md rounded-xl px-8 py-12 text-center">
      <ShieldX :size="36" class="mx-auto text-red-500" />
      <p class="mt-5 text-xs font-semibold uppercase tracking-[0.18em] text-red-500">
        403 Forbidden
      </p>
      <h1 class="mt-2 text-xl font-semibold text-ink">当前账号无权访问</h1>
      <p class="mt-3 text-sm leading-6 text-muted">请切换拥有对应角色的账号，或返回工作台。</p>
      <RouterLink
        to="/"
        class="mt-6 inline-flex rounded-lg bg-brand px-4 py-2.5 text-sm font-medium text-white"
      >
        返回工作台
      </RouterLink>
    </div>
  </main>
</template>
