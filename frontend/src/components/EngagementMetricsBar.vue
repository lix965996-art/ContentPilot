<script setup lang="ts">
import { Bookmark, Eye, Heart, MessageCircle, Share2 } from 'lucide-vue-next'
import type { ArticleEngagementTotals } from '@/types/business'

const props = defineProps<{
  totals?: ArticleEngagementTotals | null
  impressions?: number | null
  likes?: number | null
  comments?: number | null
  collects?: number | null
  shares?: number | null
  engagementRate?: number | null
  simulated?: boolean
  compact?: boolean
  label?: string
}>()

function metricValue(key: keyof ArticleEngagementTotals) {
  if (props.totals && props.totals[key] != null) return props.totals[key]
  const direct = {
    impressions: props.impressions,
    likes: props.likes,
    comments: props.comments,
    collects: props.collects,
    shares: props.shares,
    engagementTotal: null,
    engagementRate: props.engagementRate,
  }[key]
  return direct ?? null
}

function formatNum(value: number | null | undefined) {
  if (value == null) return '—'
  if (value >= 10000) return `${(value / 10000).toFixed(1)}万`
  return value.toLocaleString('zh-CN')
}
</script>

<template>
  <div class="engagement-metrics" :class="{ compact }">
    <span v-if="label" class="metrics-label">{{ label }}</span>
    <span v-if="simulated" class="metrics-badge">演示数据</span>
    <div class="metrics-items">
      <span><Eye :size="13" />浏览 {{ formatNum(metricValue('impressions') as number) }}</span>
      <span><Heart :size="13" />点赞 {{ formatNum(metricValue('likes') as number) }}</span>
      <span
        ><MessageCircle :size="13" />评论 {{ formatNum(metricValue('comments') as number) }}</span
      >
      <span><Bookmark :size="13" />收藏 {{ formatNum(metricValue('collects') as number) }}</span>
      <span v-if="!compact"><Share2 :size="13" />转发 {{ formatNum(metricValue('shares') as number) }}</span>
      <span v-if="metricValue('engagementRate') != null" class="metrics-rate">
        互动率 {{ metricValue('engagementRate') }}%
      </span>
    </div>
  </div>
</template>

<style scoped>
.engagement-metrics {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 10px 12px;
  border: 1px solid var(--sf-line, #e5e7eb);
  border-radius: 8px;
  background: #fafbfc;
}
.engagement-metrics.compact {
  padding: 0;
  border: 0;
  background: transparent;
  gap: 4px 10px;
}
.metrics-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--sf-ink, #172033);
}
.metrics-badge {
  padding: 2px 8px;
  border-radius: 999px;
  background: #fff7ed;
  color: #b54708;
  font-size: 10px;
  font-weight: 600;
}
.metrics-items {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  color: var(--sf-muted, #667085);
  font-size: 11px;
}
.compact .metrics-items {
  font-size: 10px;
  gap: 4px 8px;
}
.metrics-items span {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.metrics-rate {
  color: var(--sf-ink, #172033);
  font-weight: 600;
}
</style>
