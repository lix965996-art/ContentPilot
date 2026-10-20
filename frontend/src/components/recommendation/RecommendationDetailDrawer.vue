<script setup lang="ts">
import { computed, ref } from 'vue'
import DetailDrawer from '@/components/DetailDrawer.vue'
import HourlyActivityChart from '@/components/recommendation/HourlyActivityChart.vue'
import ContentScheduleProfilePanel from '@/components/recommendation/ContentScheduleProfilePanel.vue'
import OptimizationReasonPanel from '@/components/recommendation/OptimizationReasonPanel.vue'
import SimilarHistoryDrawer from '@/components/recommendation/SimilarHistoryDrawer.vue'
import type { RecommendationPlanRow } from '@/types/business'
import { platformNames } from '@/types/business'

const props = defineProps<{
  modelValue: boolean
  row?: RecommendationPlanRow
  confidenceLabels: Record<string, string>
}>()

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const recommendation = computed(() => props.row?.recommendation)
const highlightHour = computed(() => {
  const at = recommendation.value?.recommendedAt
  return at ? new Date(at).getHours() : undefined
})
const activity = computed(() => recommendation.value?.activityEstimate)
const learning = computed(() => recommendation.value?.optimization?.learning)
const learningReasons: Record<string, string> = {
  NO_VALIDATED_MODEL: '暂无通过评估的平台模型，使用统计推荐',
  COLD_ACCOUNT: '该账号不在模型验证范围，使用统计推荐',
  ACCOUNT_NOT_CONNECTED: '账号尚未连接，使用统计推荐',
  PLATFORM_UNSUPPORTED: '该平台使用统计推荐',
  MODEL_UNAVAILABLE: '模型不可用，已回退统计推荐',
  INFERENCE_BUDGET_EXCEEDED: '预测耗时超过预算，已回退统计推荐',
  MODEL_NOT_AVAILABLE_ASOF_DECISION: '模型训练时间晚于决策时间，已回退统计推荐',
}
const similarHistory = computed(() => recommendation.value?.similarHistory || [])
const historyOpen = ref(false)

function formatTime(value: string) {
  return new Date(value).toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <DetailDrawer
    v-model="visible"
    size="620px"
    :title="row ? `${platformNames[row.platform]} 推荐详情` : '推荐详情'"
  >
    <template v-if="recommendation && row">
      <div class="detail-summary">
        <div>
          <span>最佳时间</span><strong>{{ formatTime(recommendation.recommendedAt) }}</strong>
        </div>
        <div>
          <span>推荐得分</span><strong>{{ recommendation.score }}</strong>
        </div>
        <div>
          <span>置信度</span
          ><strong>{{
            confidenceLabels[recommendation.confidence] || recommendation.confidence
          }}</strong>
        </div>
        <div>
          <span>样本数</span><strong>{{ recommendation.sampleCount }}</strong>
        </div>
        <div>
          <span>账号样本</span><strong>{{ recommendation.accountSampleCount }}</strong>
        </div>
        <div>
          <span>公开样本</span><strong>{{ recommendation.baselineSampleCount }}</strong>
        </div>
      </div>

      <p v-if="recommendation.narrative" class="detail-narrative">{{ recommendation.narrative }}</p>
      <p v-else-if="recommendation.reasons[0]" class="detail-narrative">
        {{ recommendation.reasons[0].description }}
      </p>

      <section v-if="learning" class="detail-block panel">
        <h3>互动预测依据</h3>
        <p v-if="learning.mode === 'MACHINE_LEARNING'">
          平台模型 {{ learning.modelId }} · 目标：{{
            learning.target
          }}。预测用于候选时间评分，排期仍需满足发布约束。
        </p>
        <p v-else>
          {{ learningReasons[learning.reason || ''] || '平台模型未满足启用条件，使用统计推荐' }}
        </p>
        <template v-if="learning.mode === 'MACHINE_LEARNING' && learning.explanations.length">
          <p>
            以下解释对应模型评分最高的候选时间
            {{ learning.explanationTime }}，实际排期可能因约束调整。
          </p>
          <ul>
            <li v-for="(item, index) in learning.explanations" :key="index">
              {{ item.feature }}：{{ item.contribution > 0 ? '+' : ''
              }}{{ item.contribution }}（对数目标贡献）
            </li>
          </ul>
        </template>
      </section>

      <ContentScheduleProfilePanel
        v-if="recommendation.profile"
        class="detail-block"
        compact
        :profile="recommendation.profile"
        :profile-source="recommendation.profileSource"
      />

      <section v-if="similarHistory.length" class="detail-block panel">
        <header class="block-head">
          <h3>参考的相似历史内容（{{ recommendation.similarHistoryCount }} 篇）</h3>
          <el-button link type="primary" @click="historyOpen = true">查看全部</el-button>
        </header>
        <ul class="history-brief">
          <li
            v-for="item in similarHistory.slice(0, 3)"
            :key="`${item.refType}-${item.historicalContentId}`"
          >
            <strong>{{ item.title || `#${item.historicalContentId}` }}</strong>
            <span>
              向量相似度 {{ item.vectorSimilarity }} · LLM 相关性
              {{ item.llmRelevance === null ? '未评分' : item.llmRelevance }} · 综合
              {{ item.combinedScore }}
            </span>
          </li>
        </ul>
      </section>

      <section v-if="activity" class="detail-block panel">
        <h3>用户活跃度依据</h3>
        <ul class="fact-list">
          <li>
            主档位：{{ activity.primaryLevelLabel || activity.primaryLevel }} · 置信度
            {{ confidenceLabels[activity.confidence || ''] || activity.confidence }}
          </li>
          <li v-if="activity.primaryLevel === 'CROSS_PLATFORM_PUBLIC'" class="warn">
            该平台还没有自己的历史数据，当前活跃度来自其他平台的公开数据集（{{
              activity.crossPlatformSampleCount
            }}
            条），只作为冷启动代理，权重已额外折减。积累本平台数据后会自动切换。
          </li>
          <li>
            有效样本 {{ activity.effectiveSampleCount }} · 相似内容样本
            {{ activity.similarSampleCount }} · 账号样本 {{ activity.accountSampleCount }} ·
            平台样本 {{ activity.platformSampleCount }}
          </li>
          <li>
            时间衰减 decay_days = {{ activity.decayDays }} · 贝叶斯平滑强度
            {{ activity.priorStrength }} · 覆盖时段 {{ activity.coveredSlots }} 个
          </li>
          <li v-if="activity.priorChain?.length">
            平滑链：{{
              activity.priorChain.map((item) => `${item.label}(${item.slotCount})`).join(' → ')
            }}
          </li>
        </ul>
        <HourlyActivityChart
          v-if="!activity.hourlyCurve?.length"
          :curve="recommendation.curve"
          :highlight-hour="highlightHour"
        />
        <ul v-else class="slot-strip">
          <li
            v-for="point in activity.hourlyCurve"
            :key="point.hour"
            :class="{ on: point.hour === highlightHour }"
          >
            <i :style="{ height: `${Math.max(3, point.score)}%` }" />
            <span v-if="point.hour % 3 === 0">{{ point.hour }}</span>
          </li>
        </ul>
      </section>

      <section class="detail-block panel">
        <h3>约束与调整原因</h3>
        <OptimizationReasonPanel
          :optimization="recommendation.optimization"
          :review="recommendation.review"
          :original-best-time="recommendation.originalBestTime"
          :selected-time="recommendation.recommendedAt"
          :adjustment-reason="recommendation.adjustmentReason"
          :optimization-adjusted="recommendation.optimizationAdjusted"
        />
      </section>

      <section class="detail-alts">
        <h3>备选时段</h3>
        <div>
          <span
            v-for="item in recommendation.alternatives"
            :key="item.recommendedAt"
            class="alt-chip"
          >
            {{ formatTime(item.recommendedAt) }} · {{ item.score }}
          </span>
        </div>
      </section>

      <section
        v-if="recommendation.conflicts.length || recommendation.warnings.length"
        class="detail-warn"
      >
        <p v-for="item in recommendation.conflicts" :key="item.scheduleId">{{ item.message }}</p>
        <p v-for="(item, index) in recommendation.warnings" :key="index">{{ item }}</p>
      </section>

      <el-collapse class="detail-collapse">
        <el-collapse-item title="完整技术依据（默认收起）" name="tech">
          <ul class="tech-list">
            <li v-for="reason in recommendation.reasons" :key="reason.type">
              {{ reason.description }}（贡献 {{ reason.contribution }} 分）
            </li>
            <li>
              {{ recommendation.dataSource.baseline }} ·
              {{ recommendation.dataSource.accountHistory }}
            </li>
            <li>{{ recommendation.dataSufficiency.message }}</li>
            <li v-if="recommendation.window">分析范围：{{ recommendation.window.label }}</li>
            <li>算法版本：{{ recommendation.algorithmVersion }}</li>
            <li v-if="recommendation.stageStatus">
              阶段状态：{{
                Object.entries(recommendation.stageStatus)
                  .map(([key, value]) => `${key}=${value}`)
                  .join(' · ')
              }}
            </li>
          </ul>
        </el-collapse-item>
      </el-collapse>

      <SimilarHistoryDrawer
        v-model="historyOpen"
        :title="`${platformNames[row.platform]} 相似历史内容`"
        :items="similarHistory"
        :retrieval-provider="recommendation.retrievalProvider"
        :embedding-model="recommendation.embeddingModel"
      />
    </template>
  </DetailDrawer>
</template>

<style scoped>
.detail-summary {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}
.detail-summary div {
  border: 1px solid var(--sf-line, #e5e7eb);
  border-radius: 8px;
  padding: 8px 10px;
  background: #fafbfc;
}
.detail-summary span {
  display: block;
  color: var(--sf-muted, #667085);
  font-size: 11px;
}
.detail-summary strong {
  display: block;
  margin-top: 4px;
  color: var(--sf-ink, #172033);
  font-size: 14px;
}
.detail-narrative {
  margin: 0 0 12px;
  color: var(--sf-ink, #172033);
  font-size: 13px;
  line-height: 1.6;
}
.detail-block {
  margin-bottom: 12px;
}
.panel {
  border: 1px solid var(--sf-line, #e5e7eb);
  border-radius: 10px;
  padding: 12px 14px;
  background: #fff;
}
.panel h3,
.block-head h3 {
  margin: 0 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--sf-ink, #172033);
}
.block-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.block-head h3 {
  margin: 0;
}
.history-brief {
  margin: 8px 0 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 6px;
}
.history-brief strong {
  display: block;
  color: var(--sf-ink, #172033);
  font-size: 12px;
}
.history-brief span {
  color: var(--sf-muted, #667085);
  font-size: 11px;
}
.fact-list {
  margin: 0 0 10px;
  padding-left: 18px;
  color: var(--sf-muted, #667085);
  font-size: 12px;
  line-height: 1.7;
}
.fact-list .warn {
  color: #b54708;
}
.slot-strip {
  display: flex;
  align-items: flex-end;
  gap: 2px;
  height: 92px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.slot-strip li {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: flex-end;
  height: 100%;
}
.slot-strip i {
  width: 100%;
  border-radius: 2px 2px 0 0;
  background: #cbd5e1;
}
.slot-strip li.on i {
  background: #2563eb;
}
.slot-strip span {
  color: var(--sf-muted, #667085);
  font-size: 9px;
}
.detail-alts h3 {
  margin: 12px 0 8px;
  font-size: 13px;
}
.alt-chip {
  display: inline-block;
  margin: 0 6px 6px 0;
  border: 1px solid var(--sf-line, #e5e7eb);
  border-radius: 999px;
  padding: 4px 10px;
  font-size: 11px;
}
.detail-warn {
  margin-top: 12px;
  color: #b54708;
  font-size: 12px;
}
.detail-collapse {
  margin-top: 12px;
}
.tech-list {
  margin: 0;
  padding-left: 18px;
  color: var(--sf-muted, #667085);
  font-size: 12px;
  line-height: 1.7;
}
</style>
