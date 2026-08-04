<script setup lang="ts">
import ChartPanel from '@/components/ChartPanel.vue'

defineProps<{
  kicker: string
  title: string
  subtitle?: string
  option: unknown
  height?: string
  loading?: boolean
  hero?: boolean
  accent?: 'brand' | 'accent' | 'success' | 'neutral'
}>()
</script>

<template>
  <article
    class="analytics-chart-card"
    :class="[
      hero ? 'is-hero' : '',
      accent ? `accent-${accent}` : 'accent-brand',
    ]"
  >
    <header class="analytics-chart-header">
      <div>
        <p class="analytics-chart-kicker">{{ kicker }}</p>
        <h3 class="analytics-chart-title">{{ title }}</h3>
        <p v-if="subtitle" class="analytics-chart-subtitle">{{ subtitle }}</p>
      </div>
      <slot name="extra" />
    </header>
    <div class="analytics-chart-body">
      <ChartPanel :option="option" :height="height || '280px'" :loading="loading" />
    </div>
    <footer v-if="$slots.footer" class="analytics-chart-footer">
      <slot name="footer" />
    </footer>
  </article>
</template>

<style scoped>
.analytics-chart-card {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #fff;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
  overflow: hidden;
}
.analytics-chart-card::before {
  content: '';
  display: block;
  height: 3px;
  background: linear-gradient(90deg, #2563eb, #7c3aed);
}
.analytics-chart-card.accent-accent::before {
  background: linear-gradient(90deg, #7c3aed, #c084fc);
}
.analytics-chart-card.accent-success::before {
  background: linear-gradient(90deg, #16a34a, #4ade80);
}
.analytics-chart-card.accent-neutral::before {
  background: linear-gradient(90deg, #64748b, #94a3b8);
}
.analytics-chart-card.is-hero {
  box-shadow: 0 8px 24px rgba(37, 99, 235, 0.06);
}
.analytics-chart-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px 0;
}
.analytics-chart-kicker {
  margin: 0;
  color: #667085;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.analytics-chart-title {
  margin: 6px 0 0;
  color: #172033;
  font-size: 16px;
  font-weight: 600;
  line-height: 1.35;
}
.analytics-chart-subtitle {
  margin: 4px 0 0;
  color: #98a2b3;
  font-size: 12px;
  line-height: 1.5;
}
.analytics-chart-body {
  flex: 1;
  padding: 8px 12px 16px;
}
.analytics-chart-footer {
  border-top: 1px solid #f1f5f9;
  padding: 10px 20px 14px;
  color: #667085;
  font-size: 12px;
  line-height: 1.6;
}
</style>
