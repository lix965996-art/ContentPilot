<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import ChartPanel from '@/components/ChartPanel.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import type { PublishDecisionChain, RecommendationEffect } from '@/types/business'
import { analysisPlatformNames, platformNames } from '@/types/business'
import { AXIS_STYLE, CHART_COLORS, tooltipStyle } from '@/config/echartsTheme'

const props = defineProps<{ effect?: RecommendationEffect }>()

const platformFilter = ref('ALL')
const selectedId = ref<number | null>(null)
const chain = ref<PublishDecisionChain>()
const loading = ref(false)
const errorMessage = ref('')

function displayPlatform(name: string) {
  return analysisPlatformNames[name] || platformNames[name as keyof typeof platformNames] || name
}

/** Only schedules that actually published and have measured numbers can tell a full story. */
const candidates = computed(() =>
  (props.effect?.items || [])
    .filter((item) => item.sampleCount > 0)
    .slice()
    .reverse(),
)

const platformOptions = computed(() => {
  const seen = new Map<string, number>()
  for (const item of candidates.value) {
    seen.set(item.platform, (seen.get(item.platform) || 0) + 1)
  }
  return [...seen.entries()].map(([value, count]) => ({ value, count }))
})

const visibleCandidates = computed(() =>
  platformFilter.value === 'ALL'
    ? candidates.value
    : candidates.value.filter((item) => item.platform === platformFilter.value),
)

async function select(scheduleId: number) {
  selectedId.value = scheduleId
  loading.value = true
  errorMessage.value = ''
  try {
    chain.value = await workflowApi.publishDecision(scheduleId)
  } catch (error) {
    chain.value = undefined
    errorMessage.value = getApiErrorMessage(error, '决策链路加载失败')
  } finally {
    loading.value = false
  }
}

function selectFirst() {
  const first = visibleCandidates.value[0]
  if (first && first.scheduleId !== selectedId.value) void select(first.scheduleId)
}

watch(platformFilter, () => selectFirst())
watch(candidates, () => {
  if (!selectedId.value) selectFirst()
})
onMounted(() => selectFirst())

function formatTime(value: string | null | undefined) {
  if (!value) return '—'
  return value.replace('T', ' ').slice(0, 16)
}

function pad(value: number) {
  return String(value).padStart(2, '0')
}

function percent(value: number) {
  return `${Math.round(value * 100)}%`
}

const deviationText = computed(() => {
  const minutes = chain.value?.decision.deviationMinutes
  if (minutes === null || minutes === undefined) return '—'
  if (minutes === 0) return '准时采用'
  const abs = Math.abs(minutes)
  const label = abs >= 60 ? `${Math.floor(abs / 60)} 小时 ${abs % 60} 分` : `${abs} 分钟`
  return minutes > 0 ? `晚于推荐 ${label}` : `早于推荐 ${label}`
})

const hourlyOption = computed(() => {
  if (!chain.value) return {}
  const { hourly, hour, bestHour } = chain.value.analysis
  return {
    grid: { left: 38, right: 12, top: 16, bottom: 24 },
    tooltip: {
      ...tooltipStyle(),
      trigger: 'axis',
      formatter: (params: Array<{ name: string; value: number }>) => {
        const item = params[0]
        if (!item) return ''
        const tag =
          Number(item.name) === hour
            ? '<br/><span style="color:#2563EB">本次发布时段</span>'
            : Number(item.name) === bestHour
              ? '<br/><span style="color:#2563EB">当日最优时段</span>'
              : ''
        return `${item.name}:00<br/>活跃度得分 <b>${item.value}</b>${tag}`
      },
    },
    xAxis: {
      type: 'category',
      data: hourly.map((item) => item.hour),
      axisLabel: { color: CHART_COLORS.muted, fontSize: 10, interval: 2 },
      axisLine: { lineStyle: { color: CHART_COLORS.line } },
      axisTick: { show: false },
    },
    yAxis: { type: 'value', ...AXIS_STYLE },
    series: [
      {
        type: 'bar',
        barCategoryGap: '28%',
        data: hourly.map((item) => ({
          value: item.score,
          itemStyle: {
            color: item.hour === hour ? '#2563EB' : item.hour === bestHour ? '#93C5FD' : '#E5E9F0',
            borderRadius: [3, 3, 0, 0],
          },
        })),
      },
    ],
  }
})

const weightsOption = computed(() => {
  if (!chain.value) return {}
  const data = chain.value.analysis.components
    .filter((item) => item.weight > 0)
    .map((item) => ({ name: item.label, value: Number((item.weight * 100).toFixed(1)) }))
  return {
    color: ['#2563EB', '#60A5FA', '#93C5FD', '#CBD5E1'],
    tooltip: {
      ...tooltipStyle(),
      trigger: 'item',
      formatter: (p: { name: string; value: number }) => `${p.name}<br/>权重 <b>${p.value}%</b>`,
    },
    legend: {
      bottom: 0,
      icon: 'circle',
      itemWidth: 8,
      itemHeight: 8,
      textStyle: { color: '#667085', fontSize: 11 },
    },
    series: [
      {
        type: 'pie',
        radius: ['52%', '72%'],
        center: ['50%', '42%'],
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        data,
      },
    ],
  }
})

const contributionOption = computed(() => {
  if (!chain.value) return {}
  const items = chain.value.analysis.components
  return {
    grid: { left: 84, right: 30, top: 8, bottom: 20 },
    tooltip: {
      ...tooltipStyle(),
      trigger: 'item',
      formatter: (p: { name: string; value: number }) => `${p.name}<br/>贡献 <b>${p.value}</b> 分`,
    },
    xAxis: { type: 'value', ...AXIS_STYLE },
    yAxis: {
      type: 'category',
      data: items.map((item) => item.label).reverse(),
      axisLabel: { color: CHART_COLORS.muted, fontSize: 11 },
      axisLine: { show: false },
      axisTick: { show: false },
    },
    series: [
      {
        type: 'bar',
        barMaxWidth: 16,
        label: {
          show: true,
          position: 'right',
          fontSize: 11,
          color: '#475467',
          formatter: '{c}',
        },
        data: items
          .map((item) => ({
            value: item.contribution,
            itemStyle: { color: '#2563EB', borderRadius: [0, 4, 4, 0] },
          }))
          .reverse(),
      },
    ],
  }
})
</script>

<template>
  <section class="chain-panel">
    <aside class="chain-rail">
      <div class="rail-head">
        <h3>选择一条已发布内容</h3>
        <select v-model="platformFilter">
          <option value="ALL">全部平台（{{ candidates.length }}）</option>
          <option v-for="item in platformOptions" :key="item.value" :value="item.value">
            {{ displayPlatform(item.value) }}（{{ item.count }}）
          </option>
        </select>
      </div>
      <ul class="rail-list">
        <li v-for="item in visibleCandidates" :key="item.scheduleId">
          <button
            type="button"
            :class="{ active: item.scheduleId === selectedId }"
            @click="select(item.scheduleId)"
          >
            <span class="rail-title">{{ item.title }}</span>
            <span class="rail-meta">
              {{ displayPlatform(item.platform) }} · {{ formatTime(item.scheduledAt).slice(5) }}
              <i :class="item.timeSource === 'CUSTOM' ? 'tag-custom' : 'tag-rec'">
                {{ item.timeSource === 'CUSTOM' ? '自选' : '推荐' }}
              </i>
            </span>
          </button>
        </li>
        <li v-if="!visibleCandidates.length" class="rail-empty">
          该平台还没有已发布并回收数据的内容
        </li>
      </ul>
    </aside>

    <div class="chain-main">
      <p v-if="loading" class="chain-hint">正在还原决策链路…</p>
      <p v-else-if="errorMessage" class="chain-hint">{{ errorMessage }}</p>
      <p v-else-if="!chain" class="chain-hint">
        从左侧选择一条内容，查看它从生成到发布的完整决策过程。
      </p>

      <template v-else>
        <header class="chain-head">
          <div>
            <h2>{{ chain.title }}</h2>
            <p>
              {{ displayPlatform(chain.platform) }} · 算法 {{ chain.analysis.algorithmVersion }} ·
              {{ chain.analysis.window.label }}
            </p>
          </div>
          <span :class="chain.explainSource === 'SNAPSHOT' ? 'badge-snap' : 'badge-recalc'">
            {{ chain.explainSource === 'SNAPSHOT' ? '排期时保存的推荐快照' : '按同一时段复算' }}
          </span>
        </header>

        <ol class="steps">
          <li>
            <div class="step-no">1</div>
            <div class="step-body">
              <h4>内容适配<small>大语言模型改写与分类</small></h4>
              <div class="kv">
                <div>
                  <span>平台版本标题</span>
                  <strong>{{ chain.content.variantTitle || '—' }}</strong>
                </div>
                <div>
                  <span>生成模型</span>
                  <strong>{{ chain.content.modelName || '规则改写' }}</strong>
                </div>
                <div>
                  <span>Prompt 版本</span>
                  <strong>{{ chain.content.promptVersion || '—' }}</strong>
                </div>
                <div>
                  <span>正文字数</span>
                  <strong>{{ chain.content.wordCount ?? '—' }}</strong>
                </div>
                <div>
                  <span>内容类型</span>
                  <strong>{{ chain.content.contentTypeName }}</strong>
                </div>
                <div>
                  <span>分类方式</span>
                  <strong>
                    {{ chain.content.contentTypeProvider === 'STORED' ? '排期时判定' : '规则分类' }}
                  </strong>
                </div>
              </div>
              <p v-if="chain.content.hashtags.length" class="tags">
                <i v-for="tag in chain.content.hashtags" :key="tag">#{{ tag }}</i>
              </p>
            </div>
          </li>

          <li>
            <div class="step-no">2</div>
            <div class="step-body">
              <h4>
                用户活跃度分析<small>{{ chain.analysis.weekdayName }}全天 24 小时</small>
              </h4>
              <div class="kv">
                <div>
                  <span>账号历史样本</span>
                  <strong>{{ chain.analysis.accountSampleCount }} 条</strong>
                </div>
                <div>
                  <span>公开基线样本</span>
                  <strong>{{ chain.analysis.baselineSampleCount }} 条</strong>
                </div>
                <div>
                  <span>本次发布时段</span>
                  <strong>{{ pad(chain.analysis.hour) }}:00</strong>
                </div>
                <div>
                  <span>当日最优时段</span>
                  <strong>
                    {{ pad(chain.analysis.bestHour) }}:00（{{ chain.analysis.bestHourScore }}）
                  </strong>
                </div>
              </div>
              <ChartPanel :option="hourlyOption" height="180px" />
              <p class="legend">
                <i class="sw picked" />本次发布 <i class="sw best" />当日最优
                <i class="sw rest" />其他时段
              </p>
            </div>
          </li>

          <li>
            <div class="step-no">3</div>
            <div class="step-body">
              <h4>
                加权打分<small
                  >综合得分 {{ chain.analysis.score }} · 置信度
                  {{ chain.analysis.confidence }}</small
                >
              </h4>
              <div class="score-grid">
                <ChartPanel :option="weightsOption" height="180px" />
                <ChartPanel :option="contributionOption" height="180px" />
              </div>
              <table class="step-table">
                <thead>
                  <tr>
                    <th>维度</th>
                    <th>权重</th>
                    <th>原始分</th>
                    <th>贡献分</th>
                    <th>依据</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="item in chain.analysis.components" :key="item.type">
                    <td>{{ item.label }}</td>
                    <td>{{ percent(item.weight) }}</td>
                    <td>{{ item.rawScore }}</td>
                    <td class="accent">{{ item.contribution }}</td>
                    <td class="wrap">{{ item.description }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </li>

          <li>
            <div class="step-no">4</div>
            <div class="step-body">
              <h4>
                排期决策<small>{{ chain.decision.timeSourceLabel }}</small>
              </h4>
              <div class="kv">
                <div>
                  <span>系统推荐时间</span>
                  <strong>{{ formatTime(chain.decision.recommendedAt) }}</strong>
                </div>
                <div>
                  <span>实际排期时间</span>
                  <strong>{{ formatTime(chain.decision.scheduledAt) }}</strong>
                </div>
                <div>
                  <span>实际发布时间</span>
                  <strong>{{ formatTime(chain.decision.actualPublishAt) }}</strong>
                </div>
                <div>
                  <span>与推荐的偏差</span>
                  <strong>{{ deviationText }}</strong>
                </div>
              </div>
              <table v-if="chain.decision.alternatives.length" class="step-table">
                <thead>
                  <tr>
                    <th>备选时段</th>
                    <th>得分</th>
                    <th>样本</th>
                    <th>置信度</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="alt in chain.decision.alternatives" :key="alt.recommendedAt">
                    <td>{{ formatTime(alt.recommendedAt) }}</td>
                    <td>{{ alt.score }}</td>
                    <td>{{ alt.sampleCount }}</td>
                    <td>{{ alt.confidence }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </li>

          <li>
            <div class="step-no">5</div>
            <div class="step-body">
              <h4>
                发布效果<small>{{ chain.result.dataSources.join('、') || '暂无数据' }}</small>
              </h4>
              <div class="kv">
                <div>
                  <span>曝光</span>
                  <strong>{{ chain.result.impressions || '—' }}</strong>
                </div>
                <div>
                  <span>互动总数</span>
                  <strong>{{ chain.result.engagementTotal || '—' }}</strong>
                </div>
                <div>
                  <span>互动率</span>
                  <strong class="accent">
                    {{
                      chain.result.engagementRate !== null ? `${chain.result.engagementRate}%` : '—'
                    }}
                  </strong>
                </div>
                <div>
                  <span>指标条数</span>
                  <strong>{{ chain.result.sampleCount }}</strong>
                </div>
              </div>
            </div>
          </li>
        </ol>

        <p class="chain-note">{{ chain.explainNotice }}</p>
      </template>
    </div>
  </section>
</template>

<style scoped>
.chain-panel {
  display: grid;
  grid-template-columns: 260px minmax(0, 1fr);
  margin-top: 8px;
  background: #fff;
  border: 1px solid #e8eaed;
  border-radius: 16px;
  overflow: hidden;
}

.chain-rail {
  border-right: 1px solid #eef0f3;
  background: #fcfcfd;
  display: flex;
  flex-direction: column;
  max-height: 900px;
}

.rail-head {
  padding: 16px 14px 12px;
  border-bottom: 1px solid #eef0f3;
}

.rail-head h3 {
  margin: 0 0 10px;
  color: #111827;
  font-size: 13px;
  font-weight: 600;
}

.rail-head select {
  width: 100%;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #fff;
  color: #374151;
  font-size: 12px;
  padding: 6px 8px;
  outline: none;
}

.rail-list {
  margin: 0;
  padding: 6px;
  list-style: none;
  overflow-y: auto;
}

.rail-list button {
  width: 100%;
  border: 1px solid transparent;
  border-radius: 10px;
  background: transparent;
  padding: 9px 10px;
  text-align: left;
  cursor: pointer;
}

.rail-list button:hover {
  background: #f3f4f6;
}

.rail-list button.active {
  border-color: #bfdbfe;
  background: #eff6ff;
}

.rail-title {
  display: block;
  color: #111827;
  font-size: 12px;
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rail-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 3px;
  color: #8b93a1;
  font-size: 11px;
}

.rail-meta i {
  border-radius: 999px;
  padding: 1px 6px;
  font-size: 10px;
  font-style: normal;
}

.tag-rec {
  background: #eff6ff;
  color: #2563eb;
}

.tag-custom {
  background: #f3f4f6;
  color: #6b7280;
}

.rail-empty {
  padding: 20px 12px;
  color: #8b93a1;
  font-size: 12px;
  line-height: 1.6;
}

.chain-main {
  padding: 18px 20px 22px;
  min-width: 0;
}

.chain-hint {
  margin: 0;
  padding: 60px 0;
  color: #8b93a1;
  font-size: 13px;
  text-align: center;
}

.chain-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 14px;
  border-bottom: 1px solid #eef0f3;
}

.chain-head h2 {
  margin: 0;
  color: #111827;
  font-size: 16px;
  font-weight: 600;
}

.chain-head p {
  margin: 4px 0 0;
  color: #8b93a1;
  font-size: 12px;
}

.badge-snap,
.badge-recalc {
  flex: none;
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
}

.badge-snap {
  background: #eff6ff;
  color: #2563eb;
}

.badge-recalc {
  background: #f3f4f6;
  color: #6b7280;
}

.steps {
  margin: 0;
  padding: 0;
  list-style: none;
}

.steps > li {
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 12px;
  padding: 18px 0;
  border-bottom: 1px solid #f1f3f5;
}

.steps > li:last-child {
  border-bottom: none;
  padding-bottom: 4px;
}

.step-no {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #eff6ff;
  color: #2563eb;
  font-size: 12px;
  font-weight: 600;
  line-height: 24px;
  text-align: center;
}

.step-body {
  min-width: 0;
}

.step-body h4 {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin: 2px 0 12px;
  color: #111827;
  font-size: 14px;
  font-weight: 600;
}

.step-body h4 small {
  color: #8b93a1;
  font-size: 12px;
  font-weight: 400;
}

.kv {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: 12px 16px;
  margin-bottom: 12px;
}

.kv span {
  display: block;
  color: #8b93a1;
  font-size: 11px;
}

.kv strong {
  display: block;
  margin-top: 3px;
  color: #111827;
  font-size: 13px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
}

.accent {
  color: #2563eb;
}

.tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
}

.tags i {
  border-radius: 6px;
  background: #f3f4f6;
  color: #6b7280;
  font-size: 11px;
  font-style: normal;
  padding: 2px 7px;
}

.legend {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 6px 0 0;
  color: #8b93a1;
  font-size: 11px;
}

.sw {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 2px;
  margin-left: 8px;
}

.legend .sw:first-child {
  margin-left: 0;
}

.sw.picked {
  background: #2563eb;
}

.sw.best {
  background: #93c5fd;
}

.sw.rest {
  background: #e5e9f0;
}

.score-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.3fr);
  gap: 12px;
  margin-bottom: 8px;
}

.step-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}

.step-table th,
.step-table td {
  padding: 8px;
  text-align: left;
  border-bottom: 1px solid #f1f3f5;
  white-space: nowrap;
}

.step-table th {
  color: #8b93a1;
  font-weight: 500;
  font-size: 11px;
}

.step-table tbody tr:last-child td {
  border-bottom: none;
}

.step-table .wrap {
  color: #667085;
  white-space: normal;
  min-width: 220px;
}

.chain-note {
  margin: 14px 0 0;
  padding-top: 12px;
  border-top: 1px solid #f1f3f5;
  color: #8b93a1;
  font-size: 11px;
  line-height: 1.6;
}

@media (max-width: 1100px) {
  .chain-panel {
    grid-template-columns: 1fr;
  }

  .chain-rail {
    border-right: none;
    border-bottom: 1px solid #eef0f3;
    max-height: 280px;
  }

  .score-grid {
    grid-template-columns: 1fr;
  }
}
</style>
