<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { learningApi } from '@/api/learning'
import { getApiErrorMessage } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { LearningStatus } from '@/types/learning'

const props = defineProps<{ manageModels?: boolean; showModelManagement?: boolean }>()
const auth = useAuthStore()
const data = ref<LearningStatus | null>(null)
const loading = ref(false)
const error = ref('')
const notice = ref('')
const busy = ref<string | null>(null)
let revision = 0
let disposed = false
const showManagement = computed(
  () => (props.showModelManagement || props.manageModels) && auth.canManageSystem,
)
const canCollect = computed(() => auth.canManageBusiness)
const counts = (value: number | null) => (value === null ? '未知' : String(value))
const platformLabels: Record<string, string> = {
  BLUESKY: 'Bluesky',
  MASTODON: 'Mastodon',
  YOUTUBE: 'YouTube',
}
const algorithmLabels: Record<string, string> = { lightgbm: 'LightGBM', catboost: 'CatBoost' }
const collectionErrors: Record<string, string> = {
  AUTH_REQUIRED: '账号授权已失效，请重新连接',
  PERMISSION_DENIED: '账号暂未授予读取权限',
  POST_UNAVAILABLE: '帖子暂时无法访问',
  RATE_LIMITED: '平台请求较多，请稍后重试',
  UPSTREAM_UNAVAILABLE: '平台服务暂时不可用',
  COLLECTION_FAILED: '互动采集暂未完成，请稍后重试',
  ACCOUNT_NOT_CONNECTED: '请先连接平台账号',
  ACCOUNT_CHANGED: '发布账号已变更，请检查账号连接',
  ACCOUNT_IDENTITY_MISMATCH: '发布账号与当前连接不一致',
  WORKER_INTERRUPTED: '采集被中断，等待恢复',
  DISPATCH_EXHAUSTED: '自动采集多次失败，请手动重试',
  INVALID_RESPONSE: '平台返回数据不完整，请稍后重试',
  INVALID_POST_ID: '帖子信息不完整，暂时无法采集',
}
function collectionError(code: string | null) {
  return code ? collectionErrors[code] || '采集暂未完成，请检查账号连接后重试' : '请稍后重试'
}
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
      error.value = getApiErrorMessage(cause, '互动数据加载失败')
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
  <section class="learning-panel" aria-label="发布互动">
    <header class="learning-heading">
      <div>
        <h2>发布互动</h2>
        <p>同步 Bluesky 与 Mastodon 已发布内容的点赞、回复与转发。</p>
      </div>
      <el-button :loading="loading" @click="load">刷新互动数据</el-button>
    </header>
    <p v-if="error" role="alert" class="learning-message is-error">{{ error }}</p>
    <p v-if="notice" role="status" class="learning-message is-success">{{ notice }}</p>
    <p v-if="loading && !data" class="learning-empty">正在加载互动数据…</p>
    <template v-if="data">
      <div v-if="showManagement" class="readiness-card">
        <div class="readiness-stats">
          <div>
            <span>24小时合格样本</span
            ><strong>{{ data.readiness.accepted }}<small>条</small></strong>
          </div>
          <div>
            <span>样本账号</span><strong>{{ data.readiness.accounts }}<small>个</small></strong>
          </div>
          <div class="readiness-note">
            <strong>按真实数据推荐</strong>
            <p>没有合格平台模型时，继续使用统计推荐。</p>
          </div>
        </div>
        <details class="learning-details">
          <summary>采样标准与数据说明</summary>
          <p>
            仅使用发布后24小时至24小时15分钟内的完整观测。曝光量不可用时保持未知，不计算曝光互动率。
          </p>
          <p>采集只读取已发布帖子的互动，不会发送新帖子。</p>
          <span v-for="(count, reason) in data.readiness.reasons" :key="reason" class="reason-chip"
            >{{ reasonLabels[reason] || '其他未满足采样条件的观测' }}：{{ count }}</span
          >
        </details>
      </div>
      <div class="section-heading">
        <h3>已发布内容的互动</h3>
        <span>仅显示你的发布记录</span>
      </div>
      <div v-if="!data.items.length" class="learning-empty">
        暂无发布记录。内容发布后，可在这里查看互动。
      </div>
      <article v-for="item in data.items" :key="item.scheduleId" class="publication-card">
        <div class="publication-content">
          <div class="publication-heading">
            <strong>{{ platformLabels[item.platform] || '平台内容' }}</strong
            ><span>发布记录 {{ item.scheduleId }}</span>
          </div>
          <p class="publication-counts">
            点赞 {{ counts(item.likes) }} · 回复 {{ counts(item.replies) }} · 转发
            {{ counts(item.reposts) }}
          </p>
          <p class="publication-meta">
            {{
              item.observedAt ? `更新于 ${new Date(item.observedAt).toLocaleString()}` : '尚未采集'
            }}<span v-if="item.ageSeconds !== null"
              >，发布后 {{ (item.ageSeconds / 3600).toFixed(1) }} 小时</span
            >
          </p>
          <p v-if="item.errorCode" class="collection-error">
            {{ collectionError(item.errorCode) }}
          </p>
          <p
            v-for="task in item.tasks.filter(
              (t) => t.status === 'PENDING' || t.status === 'FAILED',
            )"
            :key="task.id"
            class="publication-meta"
            :class="{ 'collection-error': task.status === 'FAILED' }"
          >
            {{ task.windowSeconds ? `${task.windowSeconds / 3600}小时采样` : '手动采集' }}：{{
              task.status === 'PENDING'
                ? '等待执行'
                : `采集失败，${collectionError(task.errorCode)}`
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
      </article>
      <template v-if="showManagement">
        <div class="section-heading model-heading">
          <h3>模型与公开数据实验</h3>
          <span>实验结果与平台推荐独立展示</span>
        </div>
        <p v-if="!data.models.length" class="learning-empty">
          尚无本地训练模型。积累合格的平台数据后，可训练和验证平台模型。
        </p>
        <article v-for="model in data.models" :key="model.modelId" class="model-card">
          <header class="model-title">
            <strong
              >{{ platformLabels[model.platform] || '平台' }}
              {{ model.researchOnly ? '公开数据实验' : '互动预测模型' }}</strong
            ><span class="model-badge" :class="{ 'is-research': model.researchOnly }">{{
              model.researchOnly ? '仅供研究' : model.activationBlocked ? '待验证' : '可启用'
            }}</span>
          </header>
          <p v-if="model.researchOnly" class="research-note">
            公开 YouTube 回顾性实验：预测观看时长比例，不能用于
            Bluesky/Mastodon，也不证明推荐时段带来流量提升。
          </p>
          <p v-else class="model-note">
            {{ model.activationBlocked ? '未达到启用门槛，继续统计推荐' : '已达到该平台启用门槛' }}
          </p>
          <p v-if="model.researchOnly" class="model-note">
            相对基线的对数目标预测误差变化：{{
              (model.improvement.relativeImprovement * 100).toFixed(1)
            }}%（正值表示误差降低）。
          </p>
          <details class="learning-details">
            <summary>查看模型评估详情</summary>
            <dl class="model-facts">
              <div>
                <dt>算法</dt>
                <dd>{{ algorithmLabels[model.algorithm] || '预测模型' }}</dd>
              </div>
              <div>
                <dt>样本划分</dt>
                <dd>
                  训练 {{ model.trainRows }}，验证 {{ model.validationRows }}，测试
                  {{ model.testRows }}
                </dd>
              </div>
              <div>
                <dt>平均绝对误差</dt>
                <dd>{{ model.test.maeOriginal.toFixed(4) }}</dd>
              </div>
              <div>
                <dt>排序相关性</dt>
                <dd>{{ model.test.spearman?.toFixed(3) ?? '不适用' }}</dd>
              </div>
              <div>
                <dt>模型版本</dt>
                <dd class="model-id">{{ model.modelId }}</dd>
              </div>
            </dl>
          </details>
          <div v-if="showManagement" class="model-actions">
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
        </article>
        <template v-if="showManagement"
          ><el-button
            v-for="(id, platform) in data.activeModels"
            v-show="id"
            :key="platform"
            class="mt-3"
            :disabled="Boolean(busy)"
            @click="activate(String(platform), null)"
            >停用 {{ platformLabels[String(platform)] || '平台' }} 模型</el-button
          ></template
        >
      </template>
    </template>
  </section>
</template>

<style scoped>
.learning-panel {
  margin-top: 20px;
  padding: 26px;
  border: 1px solid #e4eaf2;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 8px 28px #182c4b04;
}
.learning-heading,
.section-heading,
.publication-card,
.publication-heading,
.model-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.learning-heading {
  align-items: flex-start;
}
.learning-heading h2 {
  margin: 6px 0 8px;
  color: #17263e;
  font-size: 19px;
  font-weight: 650;
  letter-spacing: -0.02em;
}
.learning-heading p,
.model-note {
  margin: 0;
  color: #66758c;
  font-size: 13px;
  line-height: 1.8;
}
.readiness-card {
  margin-top: 22px;
  padding: 20px;
  border: 1px solid #e6edf7;
  border-radius: 16px;
  background: linear-gradient(120deg, #f5f8ff, #fafcff);
}
.readiness-stats {
  display: grid;
  grid-template-columns: 1fr 1fr 2fr;
  gap: 24px;
}
.readiness-stats span {
  display: block;
  color: #697993;
  font-size: 12px;
}
.readiness-stats strong {
  display: block;
  margin-top: 6px;
  color: #294e90;
  font-size: 30px;
  line-height: 1.2;
  font-weight: 650;
}
.readiness-stats small {
  margin-left: 6px;
  font-size: 12px;
  font-weight: 400;
}
.readiness-note {
  border-left: 1px solid #dde6f3;
  padding-left: 24px;
  align-self: center;
}
.readiness-note strong {
  font-size: 14px;
  color: #30425e;
}
.readiness-note p {
  margin: 7px 0 0;
  color: #78869c;
  font-size: 12px;
}
.learning-details {
  margin-top: 16px;
  border-top: 1px solid #e8edf5;
  padding-top: 12px;
  color: #77849a;
  font-size: 12px;
  line-height: 1.8;
}
.learning-details summary {
  width: fit-content;
  cursor: pointer;
  color: #54709d;
  font-weight: 500;
}
.learning-details p {
  margin: 10px 0 0;
}
.reason-chip {
  display: inline-block;
  margin: 8px 12px 0 0;
}
.section-heading {
  margin: 24px 0 12px;
}
.section-heading h3 {
  margin: 0;
  color: #26364d;
  font-size: 14px;
  font-weight: 600;
}
.section-heading > span {
  color: #8c98aa;
  font-size: 12px;
}
.learning-empty {
  margin: 0;
  padding: 26px 16px;
  border-radius: 12px;
  background: #f8fafc;
  color: #8290a6;
  font-size: 13px;
  text-align: center;
  line-height: 1.8;
}
.publication-card {
  padding: 18px 0;
  border-bottom: 1px solid #eef2f7;
}
.publication-heading {
  justify-content: flex-start;
  gap: 12px;
}
.publication-heading strong,
.model-title strong {
  color: #2a3e5d;
  font-size: 14px;
}
.publication-heading span {
  font-size: 11px;
  color: #96a1b2;
}
.publication-counts {
  margin: 8px 0;
  color: #475a75;
  font-size: 13px;
}
.publication-meta {
  margin: 4px 0 0;
  color: #8793a5;
  font-size: 12px;
  line-height: 1.7;
}
.collection-error {
  margin: 6px 0 0;
  color: #b76541;
  font-size: 12px;
}
.model-card {
  padding: 18px;
  margin-top: 12px;
  border: 1px solid #e7ecf3;
  border-radius: 14px;
  background: #fff;
}
.model-badge {
  flex-shrink: 0;
  padding: 3px 9px;
  border-radius: 6px;
  background: #eff6ff;
  color: #5478a8;
  font-size: 11px;
}
.model-badge.is-research {
  background: #fff7ed;
  color: #aa7138;
}
.research-note {
  margin: 12px 0 8px;
  padding: 10px 12px;
  border-radius: 9px;
  background: #fffbf3;
  color: #98713f;
  font-size: 12px;
  line-height: 1.8;
}
.model-note {
  margin-top: 10px;
  font-size: 12px;
}
.model-facts {
  margin: 12px 0 0;
}
.model-facts > div {
  display: flex;
  gap: 16px;
  margin: 6px 0;
}
.model-facts dt {
  flex: 0 0 90px;
  color: #8995a7;
}
.model-facts dd {
  margin: 0;
  color: #5f7087;
  overflow-wrap: anywhere;
}
.model-id {
  font-size: 11px;
}
.model-actions {
  margin-top: 12px;
}
.learning-message {
  margin: 16px 0 0;
  padding: 12px 14px;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.7;
}
.learning-message.is-error {
  color: #b65b51;
  background: #fff4f2;
}
.learning-message.is-success {
  color: #3a7b70;
  background: #eff9f5;
}
@media (max-width: 720px) {
  .learning-panel {
    padding: 18px;
  }
  .learning-heading,
  .publication-card {
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .readiness-stats {
    grid-template-columns: 1fr 1fr;
    gap: 20px;
  }
  .readiness-note {
    grid-column: 1 / -1;
    border-left: 0;
    border-top: 1px solid #dde6f3;
    padding: 16px 0 0;
  }
  .section-heading > span {
    display: none;
  }
  .model-title {
    align-items: flex-start;
  }
}
</style>
