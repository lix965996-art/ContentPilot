<script setup lang="ts">
import type { Platform, RecommendationPlanRow } from '@/types/business'
import { platformNames } from '@/types/business'
import PlatformIcon from '@/components/PlatformIcon.vue'

defineProps<{
  rows: RecommendationPlanRow[]
  confidenceLabels: Record<string, string>
}>()

const emit = defineEmits<{
  best: [row: RecommendationPlanRow]
  alternative: [row: RecommendationPlanRow, at: string]
  custom: [row: RecommendationPlanRow]
  skip: [row: RecommendationPlanRow]
  lock: [row: RecommendationPlanRow]
  detail: [row: RecommendationPlanRow]
}>()

const strategyLabels: Record<string, string> = {
  SIMULTANEOUS: '同时发布',
  STAGGERED: '错峰发布',
  WATERFALL: '瀑布式',
}
const urgencyLabels: Record<string, string> = {
  IMMEDIATE: '即时',
  TIMELY: '时效',
  NORMAL: '常规',
  EVERGREEN: '长青',
}

function formatTime(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function strategyText(row: RecommendationPlanRow) {
  const profile = row.recommendation?.profile
  if (!profile) return '—'
  const strategy =
    strategyLabels[profile.cross_platform_strategy] || profile.cross_platform_strategy
  const urgency = urgencyLabels[profile.urgency] || profile.urgency
  return `${strategy} · ${urgency}`
}

function sampleMix(row: RecommendationPlanRow) {
  const total = row.recommendation?.sampleCount || 0
  if (!total) return '0% / 0%'
  const account = Math.round(((row.recommendation?.accountSampleCount || 0) / total) * 100)
  const baseline = Math.round(((row.recommendation?.baselineSampleCount || 0) / total) * 100)
  return `${account}% / ${baseline}%`
}

const solverLabels: Record<string, string> = {
  OPTIMAL: '已优化',
  FEASIBLE: '方案可用',
  INFEASIBLE: '暂无可行方案',
  MODEL_INVALID: '使用统计推荐',
  UNKNOWN: '使用统计推荐',
  ORTOOLS_UNAVAILABLE: '使用统计推荐',
  NO_CANDIDATE: '暂无候选时段',
}
function solverText(row: RecommendationPlanRow) {
  if (!row.recommendation) return '尚未计算'
  return solverLabels[row.recommendation.solverStatus || ''] || '统计推荐'
}

function score(value?: number | null) {
  return value === null || value === undefined ? '—' : Math.round(value)
}
</script>

<template>
  <section class="result-table-wrap">
    <header class="result-table-head">
      <h2>跨平台推荐方案</h2>
      <span
        >{{ rows.filter((row) => !row.skipped && row.recommendation).length }} 个平台可排期</span
      >
    </header>
    <el-table :data="rows" size="small" stripe>
      <el-table-column label="平台" width="118" fixed>
        <template #default="{ row }">
          <span class="platform-cell">
            <PlatformIcon :platform="row.platform as Platform" size="sm" />
            {{ platformNames[row.platform as Platform] }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="accountName" label="平台账号" min-width="110" />
      <el-table-column label="内容策略" min-width="130">
        <template #default="{ row }">{{ strategyText(row) }}</template>
      </el-table-column>
      <el-table-column label="原始最佳时间" min-width="128">
        <template #default="{ row }">
          {{ formatTime(row.recommendation?.originalBestTime) }}
        </template>
      </el-table-column>
      <el-table-column label="优化后时间" min-width="140">
        <template #default="{ row }">
          <span v-if="!row.recommendation">—</span>
          <span v-else class="final-time">
            {{ formatTime(row.recommendation.recommendedAt) }}
            <em v-if="row.locked" class="chip lock">锁定</em>
            <em v-else-if="row.recommendation.optimizationAdjusted" class="chip adj">已调整</em>
          </span>
        </template>
      </el-table-column>
      <el-table-column label="调整原因" min-width="180" show-overflow-tooltip>
        <template #default="{ row }">{{ row.recommendation?.adjustmentReason || '—' }}</template>
      </el-table-column>
      <el-table-column label="相似历史" width="88">
        <template #default="{ row }"
          >{{ row.recommendation?.similarHistoryCount ?? '—' }} 篇</template
        >
      </el-table-column>
      <el-table-column label="活跃度得分" width="98">
        <template #default="{ row }">{{ score(row.recommendation?.activityScore) }}</template>
      </el-table-column>
      <el-table-column label="数据置信度" width="102">
        <template #default="{ row }">
          <span v-if="!row.recommendation">—</span>
          <span v-else>
            {{ confidenceLabels[row.recommendation.confidence] || row.recommendation.confidence }}
            <em v-if="row.recommendation.dataConfidence != null" class="muted">
              ({{ score(row.recommendation.dataConfidence) }})
            </em>
          </span>
        </template>
      </el-table-column>
      <el-table-column label="排期状态" width="112">
        <template #default="{ row }">{{ solverText(row) }}</template>
      </el-table-column>
      <el-table-column label="备选时间" min-width="160">
        <template #default="{ row }">
          <span v-if="!row.recommendation">—</span>
          <span v-else class="alt-list">
            <button
              v-for="item in row.recommendation.alternatives.slice(0, 2)"
              :key="item.recommendedAt"
              type="button"
              class="alt-chip"
              @click="emit('alternative', row, item.recommendedAt)"
            >
              {{ formatTime(item.recommendedAt) }}
            </button>
          </span>
        </template>
      </el-table-column>
      <el-table-column label="得分" width="66">
        <template #default="{ row }">{{ row.recommendation?.score ?? '—' }}</template>
      </el-table-column>
      <el-table-column label="账号与公开样本" width="130">
        <template #default="{ row }">
          {{ row.recommendation ? `${row.recommendation.sampleCount} · ${sampleMix(row)}` : '—' }}
        </template>
      </el-table-column>
      <el-table-column label="冲突状态" min-width="120">
        <template #default="{ row }">
          <span v-if="row.errorMessage" class="status-error">{{ row.errorMessage }}</span>
          <span v-else-if="row.skipped" class="status-muted">暂不排期</span>
          <span v-else-if="row.conflictMessage === '冲突检测失败'" class="status-error"
            >冲突检测失败，请重新计算</span
          >
          <span v-else-if="row.conflictMessage === '正在检查冲突'" class="status-muted"
            >正在检查冲突</span
          >
          <span v-else-if="row.conflictLevel === 'CONFLICT'" class="status-error">{{
            row.conflictMessage
          }}</span>
          <span v-else-if="row.conflictLevel === 'DENSITY'" class="status-warn">{{
            row.conflictMessage
          }}</span>
          <span v-else class="status-ok">无冲突</span>
        </template>
      </el-table-column>
      <el-table-column label="确认时间" min-width="170">
        <template #default="{ row }">
          <el-date-picker
            v-if="row.recommendation && !row.skipped"
            v-model="row.customAt"
            type="datetime"
            value-format="YYYY-MM-DD HH:mm"
            format="YYYY-MM-DD HH:mm"
            class="!w-full"
            @change="emit('custom', row)"
          />
          <span v-else>—</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" fixed="right" width="270">
        <template #default="{ row }">
          <template v-if="row.recommendation">
            <el-button link type="primary" @click="emit('best', row)">最佳时间</el-button>
            <el-button link @click="emit('lock', row)">{{
              row.locked ? '解锁' : '锁定'
            }}</el-button>
            <el-button link @click="emit('skip', row)">{{
              row.skipped ? '恢复排期' : '暂不排期'
            }}</el-button>
            <el-button link @click="emit('detail', row)">详情</el-button>
          </template>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<style scoped>
.result-table-wrap {
  border: 1px solid var(--sf-line, #e5e7eb);
  border-radius: 16px;
  background: #fff;
  padding: 18px;
}
.result-table-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 16px;
}
.result-table-head h2 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--sf-ink, #172033);
}
.result-table-head span {
  color: var(--sf-muted, #667085);
  font-size: 12px;
}
.platform-cell {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.final-time {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.chip {
  border-radius: 999px;
  padding: 1px 7px;
  font-size: 10px;
  font-style: normal;
}
.chip.adj {
  background: #fffaeb;
  color: #b54708;
}
.chip.lock {
  background: #eff4ff;
  color: #2563eb;
}
.muted {
  color: var(--sf-muted, #667085);
  font-style: normal;
}
.alt-list {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.alt-chip {
  border: 1px solid var(--sf-line, #e5e7eb);
  border-radius: 999px;
  background: #f8fafc;
  padding: 2px 8px;
  font-size: 11px;
  color: var(--sf-ink, #172033);
}
.status-ok {
  color: #027a48;
}
.status-warn {
  color: #b54708;
}
.status-error {
  color: #b42318;
}
.status-muted {
  color: var(--sf-muted, #667085);
}
</style>
