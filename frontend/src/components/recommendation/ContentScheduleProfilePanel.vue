<script setup lang="ts">
import { computed } from 'vue'
import { BrainCircuit, ShieldCheck, Timer } from 'lucide-vue-next'
import type {
  ContentScheduleProfile,
  Platform,
  SchedulePlanReview,
  SchedulePlanSummary,
} from '@/types/business'
import { platformNames } from '@/types/business'

const props = defineProps<{
  profile?: ContentScheduleProfile
  profileSource?: string
  plan?: SchedulePlanSummary
  /** Compact mode drops the solver strip; used inside the detail drawer. */
  compact?: boolean
}>()

const urgencyLabels: Record<string, string> = {
  IMMEDIATE: '即时',
  TIMELY: '时效',
  NORMAL: '常规',
  EVERGREEN: '长青',
}
const readingModeLabels: Record<string, string> = {
  FRAGMENT: '碎片浏览',
  IMMERSIVE: '沉浸阅读',
  REFERENCE: '工具查阅',
}
const loadLabels: Record<string, string> = { LOW: '低', MEDIUM: '中', HIGH: '高' }
const strategyLabels: Record<string, string> = {
  SIMULTANEOUS: '同时发布',
  STAGGERED: '错峰发布',
  WATERFALL: '瀑布式先后',
}
const verdictLabels: Record<string, string> = {
  APPROVE: '通过',
  REQUEST_RESOLVE: '要求重新求解',
  MANUAL_REVIEW: '需人工复核',
}

const review = computed<SchedulePlanReview | undefined>(() => props.plan?.review ?? undefined)
const sourceLabel = computed(() =>
  (props.profileSource || props.plan?.profileSource) === 'LLM' ? '智能分析' : '规则分析',
)
const isFallback = computed(() => (props.profileSource || props.plan?.profileSource) !== 'LLM')

function platformLabel(code: string) {
  return platformNames[code as Platform] || code
}
</script>

<template>
  <section v-if="profile" class="profile-panel">
    <header>
      <h3><BrainCircuit :size="15" />内容排期画像</h3>
      <span class="tag" :class="{ fallback: isFallback }">{{ sourceLabel }}</span>
    </header>

    <div class="profile-grid">
      <div>
        <span>主题</span><strong>{{ profile.topic }}</strong>
      </div>
      <div>
        <span>内容类型</span><strong>{{ profile.contentTypeName || profile.content_type }}</strong>
      </div>
      <div>
        <span>目标读者</span><strong>{{ profile.target_audience }}</strong>
      </div>
      <div>
        <span>阅读场景</span>
        <strong>{{ readingModeLabels[profile.reading_mode] || profile.reading_mode }}</strong>
      </div>
      <div>
        <span>预计阅读</span><strong>{{ profile.estimated_reading_minutes }} 分钟</strong>
      </div>
      <div>
        <span>时效性</span>
        <strong>
          {{ urgencyLabels[profile.urgency] || profile.urgency }} · 保鲜
          {{ profile.freshness_hours }} 小时
        </strong>
      </div>
      <div>
        <span>认知负荷</span>
        <strong>{{ loadLabels[profile.cognitive_load] || profile.cognitive_load }}</strong>
      </div>
      <div>
        <span>跨平台策略</span>
        <strong>
          {{ strategyLabels[profile.cross_platform_strategy] || profile.cross_platform_strategy }}
          · 最小间隔 {{ profile.minimum_cross_platform_gap_minutes }} 分钟
        </strong>
      </div>
      <div>
        <span>平台优先级</span>
        <strong>{{ profile.platform_priority.map(platformLabel).join('、') }}</strong>
      </div>
    </div>

    <ul class="evidence">
      <li v-for="(item, index) in profile.reason_evidence" :key="index">{{ item }}</li>
    </ul>

    <div v-if="!compact && plan" class="solver-strip">
      <span
        ><Timer :size="13" />{{
          plan.optimizationApplied ? '联合排期已完成' : '使用统计推荐'
        }}</span
      >
      <span>{{ plan.optimizationApplied ? '已应用联合优化结果' : '使用原始统计推荐' }}</span>
      <span v-if="review" class="verdict" :class="review.verdict.toLowerCase()">
        <ShieldCheck :size="13" />方案审查：{{ verdictLabels[review.verdict] || review.verdict }}
        <template v-if="review.resolveApplied">（已按要求重新求解一次）</template>
      </span>
    </div>
    <p v-if="!compact && review?.summary" class="review-summary">{{ review.summary }}</p>
  </section>
</template>

<style scoped>
.profile-panel {
  border: 1px solid var(--sf-line, #e5e7eb);
  border-radius: 16px;
  background: #fff;
  padding: 20px;
}
.profile-panel header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.profile-panel h3 {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--sf-ink, #172033);
}
.tag {
  border-radius: 999px;
  background: #eff4ff;
  color: #2563eb;
  padding: 2px 10px;
  font-size: 11px;
}
.tag.fallback {
  background: #fffaeb;
  color: #b54708;
}
.profile-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}
.profile-grid div {
  border: 1px solid var(--sf-line, #e5e7eb);
  border-radius: 8px;
  background: #fafbfc;
  padding: 7px 10px;
}
.profile-grid span {
  display: block;
  color: var(--sf-muted, #667085);
  font-size: 12px;
}
.profile-grid strong {
  display: block;
  margin-top: 3px;
  color: var(--sf-ink, #172033);
  font-size: 12px;
  font-weight: 600;
  line-height: 1.5;
}
.evidence {
  margin: 10px 0 0;
  padding-left: 18px;
  color: var(--sf-muted, #667085);
  font-size: 12px;
  line-height: 1.7;
}
.solver-strip {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin-top: 10px;
  border-top: 1px dashed var(--sf-line, #e5e7eb);
  padding-top: 9px;
  color: var(--sf-muted, #667085);
  font-size: 12px;
}
.solver-strip span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
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
.review-summary {
  margin: 8px 0 0;
  color: var(--sf-ink, #172033);
  font-size: 12px;
  line-height: 1.6;
}
@media (max-width: 640px) {
  .profile-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .profile-panel {
    padding: 16px;
  }
}
</style>
