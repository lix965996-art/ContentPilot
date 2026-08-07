<script setup lang="ts">
import { computed } from 'vue'
import type { OptimizationDetail, Platform, SchedulePlanReview } from '@/types/business'
import { platformNames } from '@/types/business'

const props = defineProps<{
  optimization?: OptimizationDetail
  review?: SchedulePlanReview | null
  originalBestTime?: string | null
  selectedTime?: string | null
  adjustmentReason?: string
  optimizationAdjusted?: boolean
}>()

const verdictLabels: Record<string, string> = {
  APPROVE: '通过，可交用户确认',
  REQUEST_RESOLVE: '要求以更严格的软约束重新求解',
  MANUAL_REVIEW: '信息不足或风险较高，需人工检查',
}

const breakdown = computed(() => props.optimization?.softObjectiveBreakdown || {})
const hardConstraints = computed(() => props.optimization?.hardConstraints || [])
const candidates = computed(() =>
  (props.optimization?.candidates || []).filter((item) => item.candidateStatus !== 'ELIGIBLE'),
)

function formatTime(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function platformLabel(code: string) {
  return platformNames[code as Platform] || code
}
</script>

<template>
  <section class="reason-panel">
    <div class="time-diff">
      <div>
        <span>原始最佳时间（hybrid-v2）</span><strong>{{ formatTime(originalBestTime) }}</strong>
      </div>
      <div>
        <span>联合优化后时间</span>
        <strong :class="{ changed: optimizationAdjusted }">{{ formatTime(selectedTime) }}</strong>
      </div>
    </div>
    <p class="adjust-reason">{{ adjustmentReason || '未进行优化调整' }}</p>

    <h4>硬约束检查</h4>
    <ul class="constraint-list">
      <li v-for="(item, index) in hardConstraints" :key="`${item.code}-${index}`">
        <em :class="{ bad: !item.satisfied }">{{ item.code }}</em>
        <span>
          <template v-if="item.platform && item.platform !== 'ALL'">
            {{ platformLabel(item.platform) }} ·
          </template>
          {{ item.description }}
        </span>
      </li>
      <li v-if="!hardConstraints.length"><span>本次未执行联合求解，无硬约束记录。</span></li>
    </ul>

    <h4>软目标与权重</h4>
    <ul class="constraint-list">
      <li v-for="item in breakdown.objectives || []" :key="item.code">
        <em>{{ item.code }}</em>
        <span>{{ item.name }}</span>
      </li>
    </ul>
    <p v-if="breakdown.weights" class="weights">
      权重：{{
        Object.entries(breakdown.weights)
          .map(([key, value]) => `${key} ${value}`)
          .join(' · ')
      }}
    </p>
    <p v-if="breakdown.strategy" class="weights">
      策略 {{ breakdown.strategy }} · 最小间隔 {{ breakdown.minimumGapMinutes }} 分钟 · 同时发布对数
      {{ breakdown.simultaneousPairs ?? 0 }}
      <template v-if="breakdown.platformPriority?.length">
        · 优先级 {{ breakdown.platformPriority.map(platformLabel).join(' → ') }}
      </template>
    </p>

    <template v-if="candidates.length">
      <h4>被硬约束排除的候选时段（节选）</h4>
      <ul class="constraint-list">
        <li v-for="item in candidates.slice(0, 6)" :key="item.candidateTime">
          <em class="bad">{{ item.candidateStatus }}</em>
          <span>{{ formatTime(item.candidateTime) }} · {{ item.rejectReason }}</span>
        </li>
      </ul>
    </template>

    <template v-if="review">
      <h4>LLM 方案审查</h4>
      <p class="verdict" :class="review.verdict.toLowerCase()">
        {{ verdictLabels[review.verdict] || review.verdict }}
        <span v-if="review.provider">（{{ review.provider }}）</span>
      </p>
      <p class="review-text">{{ review.summary }}</p>
      <ul v-if="review.risks?.length" class="constraint-list">
        <li v-for="(risk, index) in review.risks" :key="index">
          <em>风险</em><span>{{ risk }}</span>
        </li>
      </ul>
      <p v-if="review.resolve_request" class="review-text">
        重新求解要求：最小间隔
        {{ review.resolve_request.minimum_cross_platform_gap_minutes ?? '不变' }} 分钟
        <template v-if="review.resolve_request.platform_order?.length">
          · 平台顺序 {{ review.resolve_request.platform_order.map(platformLabel).join(' → ') }}
        </template>
        · {{ review.resolveApplied ? '已重新求解一次' : '重新求解未产生可行解，保留原方案' }}
      </p>
      <p class="review-text muted">
        LLM 只能给出结论与新的软约束，不能直接指定发布时间或修改排期数据。
      </p>
    </template>
  </section>
</template>

<style scoped>
.reason-panel {
  font-size: 12px;
}
.time-diff {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.time-diff div {
  border: 1px solid var(--sf-line, #e5e7eb);
  border-radius: 8px;
  background: #fafbfc;
  padding: 8px 10px;
}
.time-diff span {
  display: block;
  color: var(--sf-muted, #667085);
  font-size: 11px;
}
.time-diff strong {
  display: block;
  margin-top: 3px;
  color: var(--sf-ink, #172033);
  font-size: 13px;
}
.time-diff strong.changed {
  color: #b54708;
}
.adjust-reason {
  margin: 8px 0 0;
  color: var(--sf-ink, #172033);
  line-height: 1.6;
}
h4 {
  margin: 14px 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--sf-ink, #172033);
}
.constraint-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 4px;
}
.constraint-list li {
  display: flex;
  gap: 8px;
  color: var(--sf-muted, #667085);
  line-height: 1.6;
}
.constraint-list em {
  flex: 0 0 auto;
  border-radius: 4px;
  background: #f2f4f7;
  padding: 0 6px;
  font-style: normal;
  font-size: 11px;
  color: #475467;
}
.constraint-list em.bad {
  background: #fee4e2;
  color: #b42318;
}
.weights {
  margin: 6px 0 0;
  color: var(--sf-muted, #667085);
  line-height: 1.6;
}
.verdict {
  margin: 0 0 4px;
  font-weight: 600;
}
.verdict.approve {
  color: #027a48;
}
.verdict.request_resolve {
  color: #b54708;
}
.verdict.manual_review {
  color: #b42318;
}
.review-text {
  margin: 0 0 6px;
  color: var(--sf-ink, #172033);
  line-height: 1.6;
}
.review-text.muted {
  color: var(--sf-muted, #667085);
}
</style>
