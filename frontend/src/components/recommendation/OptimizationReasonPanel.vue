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
  APPROVE: '检查通过，可确认排期',
  REQUEST_RESOLVE: '建议调整间隔或平台顺序后重新安排',
  MANUAL_REVIEW: '信息不足或风险较高，需人工检查',
}

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
        <span>统计推荐时间</span><strong>{{ formatTime(originalBestTime) }}</strong>
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
        <em :class="{ bad: !item.satisfied }">{{ item.satisfied ? '通过' : '需调整' }}</em>
        <span>
          <template v-if="item.platform && item.platform !== 'ALL'">
            {{ platformLabel(item.platform) }} ·
          </template>
          {{ item.description }}
        </span>
      </li>
      <li v-if="!hardConstraints.length"><span>本次未执行联合求解，无硬约束记录。</span></li>
    </ul>

    <details v-if="candidates.length" class="advanced-reasons">
      <summary>查看其他时段未采用的原因</summary>
      <template v-if="candidates.length">
        <h4>被硬约束排除的候选时段（节选）</h4>
        <ul class="constraint-list">
          <li v-for="item in candidates.slice(0, 6)" :key="item.candidateTime">
            <em class="bad">不可用</em>
            <span>{{ formatTime(item.candidateTime) }} · {{ item.rejectReason }}</span>
          </li>
        </ul>
      </template>
    </details>

    <template v-if="review">
      <h4>智能方案审查</h4>
      <p class="verdict" :class="review.verdict.toLowerCase()">
        {{ verdictLabels[review.verdict] || review.verdict }}
      </p>
      <p class="review-text">{{ review.summary }}</p>
      <ul v-if="review.risks?.length" class="constraint-list">
        <li v-for="(risk, index) in review.risks" :key="index">
          <em>风险</em><span>{{ risk }}</span>
        </li>
      </ul>
      <p v-if="review.resolve_request" class="review-text">
        建议发布间隔：至少
        {{ review.resolve_request.minimum_cross_platform_gap_minutes ?? '不变' }} 分钟
        <template v-if="review.resolve_request.platform_order?.length">
          · 平台顺序 {{ review.resolve_request.platform_order.map(platformLabel).join('、') }}
        </template>
        · {{ review.resolveApplied ? '已据此调整排期' : '暂未找到合适的新时间，保留原方案' }}
      </p>
      <p class="review-text muted">智能审查只提供排期建议，实际发布时间以你确认的排期为准。</p>
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
.advanced-reasons {
  margin-top: 14px;
  border-top: 1px solid var(--sf-line, #e5e7eb);
  padding-top: 12px;
}
.advanced-reasons summary {
  color: #54709d;
  cursor: pointer;
  font-size: 12px;
}
</style>
