<script setup lang="ts">
import type { Article, Platform, PlatformAccount, TimeWindow } from '@/types/business'
import { platformNames } from '@/types/business'
import PlatformAccountSelector from '@/components/recommendation/PlatformAccountSelector.vue'

defineProps<{
  articles: Article[]
  articleId?: number
  selectedPlatforms: Platform[]
  contentType: string
  contentTypes: Array<{ value: string; label: string }>
  recommendWindow: TimeWindow
  recommendStartDate: string
  recommendEndDate: string
  canCalculate: boolean
  calculateHint: string
  loading: boolean
  platformOptions: Platform[]
  timeWindowOptions: Array<{ value: TimeWindow; label: string }>
  accountByPlatform: Partial<Record<Platform, number>>
  accountsFor: (platform: Platform) => PlatformAccount[]
}>()

const emit = defineEmits<{
  'update:articleId': [value: number | undefined]
  'update:selectedPlatforms': [value: Platform[]]
  'update:contentType': [value: string]
  'update:recommendWindow': [value: TimeWindow]
  'update:recommendStartDate': [value: string]
  'update:recommendEndDate': [value: string]
  'update:account': [platform: Platform, accountId: number | undefined]
  calculate: []
  'article-change': []
}>()
</script>

<template>
  <section class="batch-form">
    <div class="batch-form-grid">
      <label class="field-label">
        内容
        <el-select
          :model-value="articleId"
          filterable
          class="mt-2 w-full"
          @update:model-value="emit('update:articleId', $event as number)"
          @change="emit('article-change')"
        >
          <el-option v-for="item in articles" :key="item.id" :label="item.title" :value="item.id" />
        </el-select>
      </label>

      <label class="field-label sm:col-span-2">
        目标平台（多选）
        <el-checkbox-group
          :model-value="selectedPlatforms"
          class="platform-checks mt-2"
          @update:model-value="emit('update:selectedPlatforms', $event as Platform[])"
        >
          <el-checkbox v-for="key in platformOptions" :key="key" :value="key">
            {{ platformNames[key] }}
          </el-checkbox>
        </el-checkbox-group>
      </label>

      <label class="field-label">
        内容类型
        <el-select
          :model-value="contentType"
          clearable
          filterable
          class="mt-2 w-full"
          placeholder="默认使用 AI 识别结果"
          @update:model-value="emit('update:contentType', ($event as string) || '')"
        >
          <el-option
            v-for="item in contentTypes"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
      </label>

      <label class="field-label">
        历史数据范围
        <el-select
          :model-value="recommendWindow"
          class="mt-2 w-full"
          @update:model-value="emit('update:recommendWindow', $event as TimeWindow)"
        >
          <el-option
            v-for="item in timeWindowOptions"
            :key="item.value"
            :label="item.label"
            :value="item.value"
          />
        </el-select>
      </label>

      <template v-if="recommendWindow === 'CUSTOM'">
        <label class="field-label">
          开始日期
          <el-date-picker
            :model-value="recommendStartDate"
            type="date"
            value-format="YYYY-MM-DD"
            class="mt-2 w-full"
            @update:model-value="emit('update:recommendStartDate', ($event as string) || '')"
          />
        </label>
        <label class="field-label">
          结束日期
          <el-date-picker
            :model-value="recommendEndDate"
            type="date"
            value-format="YYYY-MM-DD"
            class="mt-2 w-full"
            @update:model-value="emit('update:recommendEndDate', ($event as string) || '')"
          />
        </label>
      </template>
    </div>

    <PlatformAccountSelector
      :platforms="selectedPlatforms"
      :account-by-platform="accountByPlatform"
      :accounts-for="accountsFor"
      @update:account="(platform, accountId) => emit('update:account', platform, accountId)"
    />

    <div class="batch-form-actions">
      <p v-if="calculateHint" class="form-hint">{{ calculateHint }}</p>
      <el-button
        type="primary"
        :loading="loading"
        :disabled="!canCalculate"
        @click="emit('calculate')"
      >
        计算跨平台推荐时间
      </el-button>
    </div>
  </section>
</template>

<style scoped>
.batch-form {
  border: 1px solid var(--sf-line, #e5e7eb);
  border-radius: 18px;
  background: #fff;
  padding: 24px;
}
.batch-form-grid {
  display: grid;
  gap: 20px 24px;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.platform-checks {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
}
.batch-form-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 20px;
  padding-top: 20px;
  border-top: 1px solid var(--sf-line, #e5e7eb);
}
.form-hint {
  margin: 0;
  color: #b54708;
  font-size: 12px;
}
@media (max-width: 960px) {
  .batch-form-grid {
    grid-template-columns: 1fr;
  }
}
</style>
