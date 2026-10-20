<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { learningApi } from '@/api/learning'
import { getApiErrorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { LearningStatus } from '@/types/learning'

defineProps<{ manageModels?: boolean }>()
const auth = useAuthStore()
const data = ref<LearningStatus | null>(null)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const busy = ref<string | null>(null)
let revision = 0
let disposed = false
const canCollect = computed(() => auth.canManageBusiness)
const counts = (value: number | null) => (value === null ? '未知' : String(value))
const reasonLabels: Record<string, string> = {
  NO_PUBLICATION_SNAPSHOT: '缺少发布时快照',
  OUTSIDE_24H_WINDOW: '不在24小时采样窗口',
  DIFFERENT_TARGET_WINDOW: '其他采样窗口',
  MISSING_COUNTS: '平台未提供完整计数',
  COLLECTION_FAILED: '采集失败',
  UNKNOWN_PUBLICATION_TIME: '发布时间未知',
  FEATURE_NOT_AVAILABLE_AT_PUBLICATION: '特征晚于发布时间',
  DUPLICATE_POST: '重复帖子观测',
}
async function load() {
  const current = ++revision
  loading.value = true
  error.value = ''
  try {
    const result = await learningApi.status()
    if (!disposed && current === revision) data.value = result
  } catch (cause) {
    if (!disposed && current === revision)
      error.value = getApiErrorMessage(cause, '互动学习数据加载失败')
  } finally {
    if (!disposed && current === revision) loading.value = false
  }
}
async function collect(id: number) {
  if (busy.value || !canCollect.value) return
  busy.value = String(id)
  notice.value = ''
  error.value = ''
  try {
    await learningApi.collect(id, globalThis.crypto.randomUUID())
    if (disposed) return
    notice.value = '采集任务已保存，后台会读取互动数据；稍后刷新查看结果。'
    await load()
  } catch (cause) {
    if (!disposed) error.value = getApiErrorMessage(cause, '采集任务提交失败')
  } finally {
    if (!disposed) busy.value = null
  }
}
async function activate(platform: string, id: string | null) {
  if (busy.value || !auth.canManageSystem) return
  busy.value = id || platform
  error.value = ''
  try {
    await learningApi.activate(platform, id)
    if (!disposed) await load()
  } catch (cause) {
    if (!disposed) error.value = getApiErrorMessage(cause, '模型切换失败')
  } finally {
    if (!disposed) busy.value = null
  }
}
onMounted(load)
onUnmounted(() => {
  disposed = true
  revision += 1
})
</script>

<template>
  <section
    class="mt-4 rounded-xl border border-slate-200 bg-white p-5"
    aria-label="互动采集与机器学习"
  >
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-base font-semibold text-slate-900">互动采集与机器学习</h2>
        <p class="mt-1 text-sm text-slate-500">
          Bluesky / Mastodon 发布后自动在 1、24、72 小时读取互动，不会发送新帖子。
        </p>
      </div>
      <el-button :loading="loading" @click="load">刷新互动数据</el-button>
    </div>
    <p v-if="error" role="alert" class="mt-3 text-sm text-red-600">{{ error }}</p>
    <p v-if="notice" role="status" class="mt-3 text-sm text-blue-600">{{ notice }}</p>
    <p v-if="loading && !data" class="mt-4 text-sm text-slate-500">正在加载互动学习数据…</p>
    <template v-if="data">
      <div class="my-4 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
        <strong class="text-slate-900">24小时合格样本：{{ data.readiness.accepted }}</strong>
        · {{ data.readiness.accounts }} 个账号。仅使用发布后24小时至24小时15分钟内的完整观测。
        <p class="mt-1">
          曝光量不可用时保持未知，不计算虚假的曝光互动率。没有合格平台模型时继续使用统计推荐。
        </p>
        <span
          v-for="(count, reason) in data.readiness.reasons"
          :key="reason"
          class="mr-3 mt-1 inline-block"
          >{{ reasonLabels[reason] || reason }}：{{ count }}</span
        >
      </div>
      <p v-if="!data.items.length" class="text-sm text-slate-500">
        暂无你已发布的 Bluesky / Mastodon 帖子。可以先查看下方公开数据实验。
      </p>
      <div
        v-for="item in data.items"
        :key="item.scheduleId"
        class="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 py-3 text-sm"
      >
        <div>
          <strong>{{ item.platform }} #{{ item.scheduleId }}</strong>
          <span class="ml-3"
            >点赞 {{ counts(item.likes) }} · 回复 {{ counts(item.replies) }} · 转发
            {{ counts(item.reposts) }}</span
          >
          <p class="mt-1 text-xs text-slate-500">
            {{
              item.observedAt ? `观测于 ${new Date(item.observedAt).toLocaleString()}` : '尚未采集'
            }}
            <span v-if="item.ageSeconds !== null">
              · 发布后 {{ (item.ageSeconds / 3600).toFixed(1) }} 小时</span
            >
            <span v-if="item.errorCode" class="text-red-600"> · {{ item.errorCode }}</span>
          </p>
          <p
            v-for="task in item.tasks.filter(
              (t) => t.status === 'PENDING' || t.status === 'FAILED',
            )"
            :key="task.id"
            class="mt-1 text-xs text-slate-500"
          >
            {{ task.windowSeconds ? `${task.windowSeconds / 3600}小时采样` : '手动采集' }}：{{
              task.status === 'PENDING' ? '等待执行' : `失败 ${task.errorCode || ''}`
            }}
          </p>
        </div>
        <el-button
          v-if="canCollect"
          :loading="busy === String(item.scheduleId)"
          :disabled="Boolean(busy)"
          @click="collect(item.scheduleId)"
          >采集最新互动</el-button
        >
      </div>
      <div class="mt-4 border-t border-slate-100 pt-4">
        <h3 class="text-sm font-semibold">模型与公开数据实验</h3>
        <p v-if="!data.models.length" class="mt-2 text-sm text-slate-500">
          尚无本地训练模型。平台数据不足时不会伪造训练结果。
        </p>
        <div
          v-for="model in data.models"
          :key="model.modelId"
          class="mt-3 rounded-lg border border-slate-200 p-3 text-sm"
        >
          <strong>{{ model.platform }} · {{ model.algorithm }} · {{ model.modelId }}</strong>
          <p class="mt-1 text-slate-600">
            训练 {{ model.trainRows }} / 验证 {{ model.validationRows }} / 测试
            {{ model.testRows }}；原始目标 MAE {{ model.test.maeOriginal.toFixed(4) }}；Spearman
            {{ model.test.spearman?.toFixed(3) ?? '不适用' }}
          </p>
          <p v-if="model.researchOnly" class="mt-2 text-amber-700">
            公开 YouTube 回顾性实验：预测观看时长比例，不能用于
            Bluesky/Mastodon，也不证明推荐时段带来流量提升。
          </p>
          <p v-else class="mt-1 text-slate-500">
            {{ model.activationBlocked ? '未达到启用门槛，继续统计推荐' : '已达到该平台启用门槛' }}
          </p>
          <p v-if="model.researchOnly" class="mt-1 text-slate-500">
            相对基线的对数目标预测误差变化：{{
              (model.improvement.relativeImprovement * 100).toFixed(1)
            }}%（正值表示误差降低）。
          </p>
          <div v-if="manageModels && auth.canManageSystem" class="mt-2 flex gap-2">
            <el-button
              size="small"
              :disabled="
                Boolean(model.activationBlocked) ||
                Boolean(busy) ||
                data.activeModels[model.platform] === model.modelId
              "
              @click="activate(model.platform, model.modelId)"
              >{{
                data.activeModels[model.platform] === model.modelId ? '当前使用' : '启用模型'
              }}</el-button
            >
          </div>
        </div>
        <template v-if="manageModels && auth.canManageSystem">
          <el-button
            v-for="(id, platform) in data.activeModels"
            v-show="id"
            :key="platform"
            class="mt-3"
            :disabled="Boolean(busy)"
            @click="activate(String(platform), null)"
            >停用 {{ platform }} 模型</el-button
          >
        </template>
      </div>
    </template>
  </section>
</template>
