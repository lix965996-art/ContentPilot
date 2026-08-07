<script setup lang="ts">
import type { Platform, PlatformAccount } from '@/types/business'
import { platformNames } from '@/types/business'

defineProps<{
  platforms: Platform[]
  accountByPlatform: Partial<Record<Platform, number>>
  accountsFor: (platform: Platform) => PlatformAccount[]
}>()

const emit = defineEmits<{
  'update:account': [platform: Platform, accountId: number | undefined]
}>()
</script>

<template>
  <section v-if="platforms.length" class="account-grid">
    <label v-for="platform in platforms" :key="platform" class="field-label">
      {{ platformNames[platform] }} 账号
      <el-select
        :model-value="accountByPlatform[platform]"
        class="mt-2 w-full"
        placeholder="请选择账号"
        @update:model-value="emit('update:account', platform, $event as number)"
      >
        <el-option
          v-for="account in accountsFor(platform)"
          :key="account.id!"
          :label="account.accountName"
          :value="account.id!"
        />
      </el-select>
    </label>
  </section>
</template>

<style scoped>
.account-grid {
  display: grid;
  gap: 12px 16px;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px dashed var(--sf-line, #e5e7eb);
}
@media (max-width: 960px) {
  .account-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
</style>
