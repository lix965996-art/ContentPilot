<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import FullCalendar from '@fullcalendar/vue3'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import listPlugin from '@fullcalendar/list'
import interactionPlugin, { Draggable } from '@fullcalendar/interaction'
import zhCnLocale from '@fullcalendar/core/locales/zh-cn'
import { ElMessage } from 'element-plus'
import { CircleCheck, Clock3, GripVertical, Lightbulb, Plus, TriangleAlert } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import DetailDrawer from '@/components/DetailDrawer.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import {
  accountStatusNames,
  canUseXApi,
  defaultPublishMode,
  formatLocalDateTime,
  publishModeLabel,
  publishModeOptions,
} from '@/composables/usePublishModes'
import type {
  Article,
  Platform,
  PlatformAccount,
  PublishMode,
  PublishTimeRecommendation,
  Schedule,
  ScheduleBacklogItem,
  ScheduleConflict,
  TimeSource,
  Variant,
} from '@/types/business'
import { platformColors, platformNames } from '@/types/business'
import { useAuthStore } from '@/stores/auth'

const schedules = ref<Schedule[]>([])
const backlog = ref<ScheduleBacklogItem[]>([])
const route = useRoute()
const auth = useAuthStore()
const canOperate = computed(() => auth.canManageBusiness)
const platformFilter = ref<Platform | ''>('')
const backlogQuery = ref('')
const backlogElement = ref<HTMLElement>()
let backlogDraggable: Draggable | undefined
const drawer = ref(false)
const editing = ref<Schedule>()
const dialog = ref(false)
const articles = ref<Article[]>([])
const variants = ref<Variant[]>([])
const accounts = ref<PlatformAccount[]>([])
const accountFilter = ref<number | ''>('')
const recommendation = ref<PublishTimeRecommendation>()
const recommending = ref(false)
const conflicts = ref<ScheduleConflict[]>([])
const timeSource = ref<TimeSource>('CUSTOM')
const basis = ref<Awaited<ReturnType<typeof workflowApi.scheduleRecommendationBasis>>>()
const form = ref<{
  article_id?: number
  variant_id?: number
  account_id?: number
  platform: Platform
  scheduled_at: string
  publish_mode: PublishMode
}>({ platform: 'WEIBO', scheduled_at: '', publish_mode: 'REAL_API' })
const availableAccounts = computed(() =>
  accounts.value.filter((item) => item.platform === form.value.platform && item.id),
)
const selectedAccount = computed(() =>
  availableAccounts.value.find((item) => item.id === form.value.account_id),
)
const publishModes = computed(() => publishModeOptions(form.value.platform, selectedAccount.value))
const platformGlyphs: Record<Platform, string> = {
  WEIBO: '微',
  XIAOHONGSHU: '红',
  WECHAT_OFFICIAL: '公',
  X: 'X',
  TOUTIAO: '头',
}
const filteredBacklog = computed(() =>
  backlog.value.filter(
    (item) =>
      (!platformFilter.value || item.platform === platformFilter.value) &&
      (!backlogQuery.value ||
        `${item.articleTitle}${item.variantTitle}`
          .toLowerCase()
          .includes(backlogQuery.value.toLowerCase())),
  ),
)
const filterAccounts = computed(() =>
  accounts.value.filter(
    (item) => item.id && (!platformFilter.value || item.platform === platformFilter.value),
  ),
)
const visibleSchedules = computed(() =>
  schedules.value.filter(
    (x) =>
      (!platformFilter.value || x.platform === platformFilter.value) &&
      (!accountFilter.value || x.accountId === accountFilter.value),
  ),
)
const densityAlerts = computed(() => {
  const groups = new Map<string, Schedule[]>()
  visibleSchedules.value.forEach((item) => {
    if (!item.accountId || ['CANCELLED', 'FAILED'].includes(item.status)) return
    const key = `${item.platform}-${item.accountId}`
    groups.set(key, [...(groups.get(key) || []), item])
  })
  const alerts: Array<{ key: string; label: string; count: number; day: string }> = []
  groups.forEach((rows, key) => {
    const byDay = new Map<string, number>()
    rows.forEach((row) => {
      const day = row.scheduledAt.slice(0, 10)
      byDay.set(day, (byDay.get(day) || 0) + 1)
    })
    byDay.forEach((count, day) => {
      if (count < 3) return
      const sample = rows[0]
      alerts.push({
        key: `${key}-${day}`,
        label: `${platformNames[sample.platform]} · ${sample.accountName || '账号'}`,
        count,
        day,
      })
    })
  })
  return alerts.sort((a, b) => a.day.localeCompare(b.day))
})
const events = computed(() =>
  visibleSchedules.value.map((x) => {
    // Prefer the platform-adapted variant title so same source article looks distinct.
    const headline = (x.variantTitle || x.articleTitle || '').trim()
    return {
      id: String(x.id),
      title: `${platformGlyphs[x.platform]} ${platformNames[x.platform]} · ${headline}`,
      start: x.scheduledAt,
      backgroundColor: platformColors[x.platform],
      borderColor: platformColors[x.platform],
      classNames: [`platform-${x.platform.toLowerCase()}`],
      extendedProps: x,
    }
  }),
)
const options = computed(() => ({
  plugins: [dayGridPlugin, timeGridPlugin, listPlugin, interactionPlugin],
  locale: zhCnLocale,
  initialView: 'dayGridMonth',
  headerToolbar: {
    left: 'prev,next today',
    center: 'title',
    right: 'dayGridMonth,timeGridWeek,timeGridDay,listWeek',
  },
  height: 'auto',
  // Month cells get dense after seeding; keep three pills visible and collapse the rest.
  dayMaxEvents: 3,
  moreLinkText: (n: number) => `还有 ${n} 条`,
  moreLinkClick: 'popover',
  editable: canOperate.value,
  droppable: canOperate.value,
  eventReceive: (info: any) => {
    info.event.remove()
    const variantId = Number(info.draggedEl?.dataset.variantId)
    const item = backlog.value.find((row) => row.variantId === variantId)
    if (item) void openBacklog(item, info.event.start)
  },
  eventDrop: async (info: any) => {
    try {
      const target = info.event.extendedProps as Schedule
      const scheduledAt = formatLocalDateTime(info.event.start)
      const check = await workflowApi.scheduleConflictCheck({
        platform: target.platform,
        scheduled_at: scheduledAt,
        account_id: target.accountId || undefined,
        exclude_schedule_id: Number(info.event.id),
      })
      if (check.hasConflict) {
        info.revert()
        ElMessage.warning(check.conflicts[0]?.message || '该时段与已有排期冲突')
        return
      }
      await workflowApi.updateSchedule(Number(info.event.id), { scheduled_at: scheduledAt })
      await load()
      if (check.hasDensityWarning)
        ElMessage.warning(check.conflicts[0]?.message || '同账号发布过密')
      else ElMessage.success('排期时间已更新')
    } catch (e) {
      info.revert()
      ElMessage.error(getApiErrorMessage(e))
    }
  },
  eventClick: (info: any) => {
    void openSchedule(Number(info.event.id))
  },
}))
async function openSchedule(id: number) {
  editing.value = await workflowApi.schedule(id)
  drawer.value = true
  basis.value = undefined
  try {
    basis.value = await workflowApi.scheduleRecommendationBasis(id)
  } catch {
    basis.value = undefined
  }
}
const basisReasons = computed(() => {
  const snapshot = (basis.value?.snapshot || {}) as { reasons?: Array<{ description?: string }> }
  return (snapshot.reasons || []).map((item) => item.description).filter(Boolean) as string[]
})
const basisEvidence = computed(
  () =>
    (basis.value?.slotEvidence || {}) as {
      score?: number
      sampleCount?: number
      components?: Record<string, number>
    },
)
async function load() {
  const [scheduleRows, backlogRows] = await Promise.all([
    workflowApi.schedules(),
    workflowApi.scheduleBacklog(),
  ])
  schedules.value = scheduleRows
  backlog.value = backlogRows
  await nextTick()
  setupBacklogDrag()
}
function setupBacklogDrag() {
  backlogDraggable?.destroy()
  if (!backlogElement.value || !canOperate.value) return
  backlogDraggable = new Draggable(backlogElement.value, {
    itemSelector: '.backlog-card',
    eventData: (element) => ({
      title: element.dataset.title || '待排期内容',
      duration: '00:30',
    }),
  })
}
async function init() {
  const [data, accountRows] = await Promise.all([
    workflowApi.articles({ page_size: 100 }),
    workflowApi.platformAccounts(),
  ])
  articles.value = data.items
  accounts.value = accountRows
  await load()
  const focusId = Number(route.query.schedule)
  if (focusId) await openSchedule(focusId)
  if (route.query.create === '1') {
    openCreate()
    const articleId = Number(route.query.article)
    if (articleId && articles.value.some((item) => item.id === articleId)) {
      form.value.article_id = articleId
      await chooseArticle()
      const variantId = Number(route.query.variant)
      if (variantId && variants.value.some((item) => item.id === variantId)) {
        form.value.variant_id = variantId
        chooseVariant(variantId)
      }
    }
  }
}
async function chooseArticle() {
  if (!form.value.article_id) return
  variants.value = await workflowApi.variants(form.value.article_id)
  const first = variants.value.find((item) => item.reviewStatus === 'APPROVED') || variants.value[0]
  if (first) {
    form.value.variant_id = first.id
    form.value.platform = first.platform
    choosePlatform()
  }
}
function chooseVariant(id: number) {
  const item = variants.value.find((x) => x.id === id)
  if (item) {
    form.value.platform = item.platform
    choosePlatform()
  }
}
function choosePlatform() {
  const account = accounts.value.find((item) => item.platform === form.value.platform && item.id)
  form.value.account_id = account?.id || undefined
  form.value.publish_mode = defaultPublishMode(form.value.platform, account)
  void fetchRecommendation()
}
async function fetchRecommendation(autofill = true) {
  recommendation.value = undefined
  if (!form.value.article_id) return
  recommending.value = true
  try {
    recommendation.value = await workflowApi.recommend({
      article_id: form.value.article_id,
      variant_id: form.value.variant_id,
      platform: form.value.platform,
      account_id: form.value.account_id,
    })
    if (autofill && recommendation.value.recommendedAt) applyRecommendedTime()
  } catch (e) {
    ElMessage.warning(getApiErrorMessage(e))
  } finally {
    recommending.value = false
    await checkConflict()
  }
}
function applyRecommendedTime() {
  if (!recommendation.value?.recommendedAt) return
  form.value.scheduled_at = recommendation.value.recommendedAt.slice(0, 16)
  timeSource.value = 'RECOMMENDED'
  void checkConflict()
}
function applyAlternative(value: string) {
  form.value.scheduled_at = value.slice(0, 16)
  timeSource.value = 'ALTERNATIVE'
  void checkConflict()
}
function markCustomTime() {
  const picked = form.value.scheduled_at
  const best = recommendation.value?.recommendedAt?.slice(0, 16)
  const alternatives = (recommendation.value?.alternatives || []).map((item) =>
    item.recommendedAt.slice(0, 16),
  )
  if (picked === best) timeSource.value = 'RECOMMENDED'
  else if (alternatives.includes(picked)) timeSource.value = 'ALTERNATIVE'
  else timeSource.value = 'CUSTOM'
  void checkConflict()
}
async function checkConflict() {
  conflicts.value = []
  if (!form.value.scheduled_at) return
  try {
    const result = await workflowApi.scheduleConflictCheck({
      platform: form.value.platform,
      scheduled_at: `${form.value.scheduled_at}:00`,
      account_id: form.value.account_id,
    })
    conflicts.value = result.conflicts
  } catch {
    conflicts.value = []
  }
}
function resetAdvisor() {
  recommendation.value = undefined
  conflicts.value = []
  timeSource.value = 'CUSTOM'
}
function openCreate() {
  resetAdvisor()
  form.value = {
    platform: 'WEIBO',
    scheduled_at: formatLocalDateTime(new Date(Date.now() + 3600000)).slice(0, 16),
    publish_mode: 'REAL_API',
  }
  dialog.value = true
}
async function openBacklog(item: ScheduleBacklogItem, date?: Date) {
  resetAdvisor()
  form.value = {
    article_id: item.articleId,
    variant_id: item.variantId,
    platform: item.platform,
    scheduled_at: formatLocalDateTime(
      date && date.getTime() > Date.now()
        ? new Date(date.getTime() + (date.getHours() === 0 ? 10 * 3600000 : 0))
        : new Date(Date.now() + 3600000),
    ).slice(0, 16),
    publish_mode: defaultPublishMode(item.platform),
  }
  variants.value = await workflowApi.variants(item.articleId)
  const account = accounts.value.find((row) => row.platform === form.value.platform && row.id)
  form.value.account_id = account?.id || undefined
  form.value.publish_mode = defaultPublishMode(form.value.platform, account)
  dialog.value = true
  // 拖到具体格子时保留用户选定的时间，仅展示推荐；点击“排期”按钮时自动填充推荐时间
  await fetchRecommendation(!date)
}
async function create() {
  try {
    if (
      (form.value.platform !== 'XIAOHONGSHU' || form.value.publish_mode === 'MCP_PUBLISH') &&
      !form.value.account_id
    ) {
      ElMessage.warning('请先在“平台账号”页面配置并选择账号')
      return
    }
    if (form.value.platform === 'X' && !canUseXApi(selectedAccount.value)) {
      ElMessage.warning('X 账号尚未完成授权，或管理员尚未开启真实发布')
      return
    }
    await workflowApi.createSchedule({
      ...form.value,
      scheduled_at: `${form.value.scheduled_at}:00`,
      recommendation_id: recommendation.value?.id,
      time_source: timeSource.value,
      content_type: recommendation.value?.contentType,
    })
    dialog.value = false
    await load()
    ElMessage.success('排期已创建')
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  }
}
onMounted(init)
onBeforeUnmount(() => backlogDraggable?.destroy())
</script>
<template>
  <div>
    <PageHeader title="排期日历" description="查看多平台发布计划，拖拽即可调整发布时间。"
      ><el-button v-if="canOperate" type="primary" @click="openCreate"
        ><Plus :size="16" class="mr-2" />新建排期</el-button
      ></PageHeader
    >
    <section class="calendar-workspace">
      <aside class="calendar-side">
        <div class="calendar-filter">
          <span>平台视图</span
          ><button :class="{ active: !platformFilter }" @click="platformFilter = ''">全部</button
          ><button
            v-for="(name, key) in platformNames"
            :key="key"
            :class="{ active: platformFilter === key }"
            @click="platformFilter = key"
          >
            <i :style="{ background: platformColors[key] }" />{{ name }}
          </button>
          <el-select
            v-model="accountFilter"
            size="small"
            clearable
            class="mt-3 w-full"
            placeholder="全部账号"
            ><el-option
              v-for="account in filterAccounts"
              :key="account.id!"
              :label="`${platformNames[account.platform]} · ${account.accountName}`"
              :value="account.id!"
          /></el-select>
        </div>
        <div v-if="densityAlerts.length" class="density-alerts">
          <b><TriangleAlert :size="13" />发布过密提示</b>
          <p v-for="item in densityAlerts" :key="item.key">
            {{ item.day }} · {{ item.label }} 当天已排 {{ item.count }} 条
          </p>
        </div>
        <div class="backlog-head">
          <div>
            <b>待排期</b><span>{{ filteredBacklog.length }}</span>
          </div>
          <small>拖到日历，或点击排期</small>
          <el-input v-model="backlogQuery" size="small" clearable placeholder="搜索内容" />
        </div>
        <div ref="backlogElement" class="backlog-list">
          <article
            v-for="item in filteredBacklog"
            :key="item.variantId"
            class="backlog-card"
            :data-variant-id="item.variantId"
            :data-title="item.articleTitle"
          >
            <GripVertical :size="14" />
            <div>
              <header>
                <i :style="{ background: platformColors[item.platform] }" />
                <span>{{ platformNames[item.platform] }}</span>
                <span v-if="item.ready" class="ready"><CircleCheck :size="11" />就绪</span>
                <span v-else class="blocked"><TriangleAlert :size="11" />需完善</span>
              </header>
              <b>{{ item.articleTitle }}</b>
              <small v-if="item.blockers.length">{{ item.blockers.join(' · ') }}</small>
              <small v-else>{{ item.variantTitle }}</small>
            </div>
            <button v-if="canOperate" @click.stop="openBacklog(item)">排期</button>
          </article>
          <p v-if="!filteredBacklog.length" class="backlog-empty">没有待排期的已审核内容</p>
        </div>
      </aside>
      <div class="calendar-shell">
        <FullCalendar :options="{ ...options, events }" />
      </div>
    </section>
    <DetailDrawer v-model="drawer" title="排期详情" size="420px"
      ><template v-if="editing"
        ><div class="space-y-5">
          <div>
            <p class="field-label">内容</p>
            <p class="mt-2 font-medium text-ink">{{ editing.articleTitle }}</p>
          </div>
          <div class="grid grid-cols-2 gap-4">
            <div>
              <p class="field-label">平台</p>
              <p class="mt-2">{{ platformNames[editing.platform] }}</p>
            </div>
            <div>
              <p class="field-label">状态</p>
              <StatusBadge class="mt-2" :status="editing.status" />
            </div>
          </div>
          <div>
            <p class="field-label">计划时间</p>
            <p class="mt-2">{{ new Date(editing.scheduledAt).toLocaleString('zh-CN') }}</p>
          </div>
          <div>
            <p class="field-label">发布方式</p>
            <p class="mt-2">{{ publishModeLabel(editing.platform, editing.publishMode) }}</p>
          </div>
          <div v-if="basis">
            <p class="field-label">推荐依据</p>
            <div class="reason-card mt-2 space-y-2">
              <p>
                时间来源：{{
                  basis.timeSource === 'RECOMMENDED'
                    ? '采用推荐时间'
                    : basis.timeSource === 'ALTERNATIVE'
                      ? '采用备选时间'
                      : '自定义时间'
                }}
                <span v-if="basis.contentTypeName"> · 内容类型：{{ basis.contentTypeName }}</span>
              </p>
              <p v-if="basis.recommendedAt">
                推荐时间：{{ new Date(basis.recommendedAt).toLocaleString('zh-CN') }}
                <span v-if="basis.deviationMinutes !== null">
                  （偏差 {{ basis.deviationMinutes }} 分钟）</span
                >
              </p>
              <p v-if="basisEvidence.score !== undefined">
                该时段得分 {{ basisEvidence.score }} · 样本 {{ basisEvidence.sampleCount ?? 0 }} 条
              </p>
              <p v-for="(text, index) in basisReasons" :key="index">· {{ text }}</p>
              <p v-if="!basisReasons.length && !basis.recommendedAt">
                该排期由人工直接选定时间，未记录推荐快照。
              </p>
            </div>
          </div>
          <div v-if="editing.logs?.length">
            <p class="field-label">执行日志</p>
            <div v-for="(log, index) in editing.logs" :key="index" class="reason-card mt-2">
              {{ log.step }} · {{ log.status }}
            </div>
          </div>
        </div></template
      ></DetailDrawer
    ><el-dialog v-model="dialog" title="新建排期" width="520px"
      ><el-form label-position="top"
        ><el-form-item label="文章" required
          ><el-select v-model="form.article_id" filterable class="w-full" @change="chooseArticle"
            ><el-option
              v-for="item in articles"
              :key="item.id"
              :label="item.title"
              :value="item.id" /></el-select></el-form-item
        ><el-form-item label="平台版本" required
          ><el-select v-model="form.variant_id" class="w-full" @change="chooseVariant"
            ><el-option
              v-for="item in variants"
              :key="item.id"
              :label="`${platformNames[item.platform]} · v${item.versionNo} · ${item.reviewStatus === 'APPROVED' ? '已审核' : '待审核'} · ${item.title}`"
              :value="item.id" /></el-select></el-form-item
        ><el-form-item label="排期时间" required
          ><el-date-picker
            v-model="form.scheduled_at"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm"
            class="!w-full"
            @change="markCustomTime" /></el-form-item
        ><el-form-item label="推荐时间">
          <div class="advisor-box">
            <p v-if="recommending" class="advisor-loading">
              <Clock3 :size="13" />正在按活跃度数据计算推荐时间…
            </p>
            <template v-else-if="recommendation">
              <p class="advisor-head">
                <Lightbulb :size="13" />
                <b>{{ new Date(recommendation.recommendedAt).toLocaleString('zh-CN') }}</b>
                <span
                  >得分 {{ recommendation.score }} · 置信度 {{ recommendation.confidence }} ·
                  {{ recommendation.contentTypeName }}</span
                >
                <button type="button" @click="applyRecommendedTime">使用推荐时间</button>
              </p>
              <p class="advisor-alts">
                <span>备选</span>
                <button
                  v-for="item in recommendation.alternatives"
                  :key="item.recommendedAt"
                  type="button"
                  @click="applyAlternative(item.recommendedAt)"
                >
                  {{ new Date(item.recommendedAt).toLocaleString('zh-CN', { hour12: false }) }} ·
                  {{ item.score }}
                </button>
              </p>
              <p v-for="(reason, index) in recommendation.reasons.slice(0, 3)" :key="index">
                · {{ reason.description }}
              </p>
              <p class="advisor-source">
                数据来源：{{ recommendation.dataSource.baseline }} ·
                {{ recommendation.dataSource.accountHistory }} ·
                {{ recommendation.dataSufficiency.message }}
              </p>
              <p
                v-for="(warn, index) in recommendation.warnings"
                :key="`w${index}`"
                class="advisor-warn"
              >
                <TriangleAlert :size="12" />{{ warn }}
              </p>
            </template>
            <p v-else class="advisor-empty">选择文章与平台后自动给出数据驱动的推荐时间。</p>
            <p v-for="item in conflicts" :key="item.scheduleId" class="advisor-warn">
              <TriangleAlert :size="12" />{{ item.message }}
            </p>
          </div> </el-form-item
        ><el-form-item
          label="平台账号"
          :required="form.platform !== 'XIAOHONGSHU' || form.publish_mode === 'MCP_PUBLISH'"
          ><el-select
            v-model="form.account_id"
            class="w-full"
            placeholder="请选择平台账号"
            @change="fetchRecommendation(false)"
            ><el-option
              v-for="account in availableAccounts"
              :key="account.id || account.platform"
              :label="`${account.accountName} · ${accountStatusNames[account.status] || account.status}`"
              :value="account.id!" /></el-select></el-form-item
        ><el-form-item label="发布方式" required
          ><el-select v-model="form.publish_mode" class="w-full"
            ><el-option
              v-for="mode in publishModes"
              :key="mode.value"
              :label="mode.label"
              :value="mode.value"
              :disabled="mode.disabled" /></el-select></el-form-item
        ><el-alert
          v-if="form.platform === 'XIAOHONGSHU'"
          :title="
            form.publish_mode === 'MCP_PUBLISH'
              ? '将通过本机 xiaohongshu-mcp 发布为“仅自己可见”；请保持本机服务运行且登录有效。'
              : '当前采用人工确认发布，不属于服务器无人值守自动发布。'
          "
          type="warning"
          :closable="false"
        />
        <el-alert
          v-else-if="form.platform === 'X'"
          :title="
            canUseXApi(selectedAccount)
              ? '该排期会在执行时通过 X 官方 API 发送真实帖子。创建排期不等于立即发布，但到点会自动执行。'
              : '当前不会发布：请先由管理员完成 X OAuth，并明确开启真实发布开关。'
          "
          :type="canUseXApi(selectedAccount) ? 'warning' : 'info'"
          :closable="false"
        />
        <el-alert
          v-else-if="form.platform === 'TOUTIAO'"
          :title="
            selectedAccount?.status === 'CONNECTED' && selectedAccount.publicPublishEnabled
              ? '到点后会使用本机 Chrome 会话向今日头条发送真实文章；遇到登录失效或安全验证会停止并提示处理。'
              : '当前不会发布：请先由管理员完成今日头条扫码登录，并开启真实发布安全开关。'
          "
          :type="
            selectedAccount?.status === 'CONNECTED' && selectedAccount.publicPublishEnabled
              ? 'warning'
              : 'info'
          "
          :closable="false"
        />
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="create">创建排期</el-button>
      </template>
    </el-dialog>
  </div>
</template>
