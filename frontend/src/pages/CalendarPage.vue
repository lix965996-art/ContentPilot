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
import { CircleCheck, GripVertical, Plus, TriangleAlert } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import DetailDrawer from '@/components/DetailDrawer.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import type {
  Article,
  Platform,
  PlatformAccount,
  PublishMode,
  Schedule,
  ScheduleBacklogItem,
  Variant,
} from '@/types/business'
import { platformColors, platformNames } from '@/types/business'
import { useAuthStore } from '@/stores/auth'

const schedules = ref<Schedule[]>([])
const backlog = ref<ScheduleBacklogItem[]>([])
const route = useRoute()
const auth = useAuthStore()
const canOperate = computed(() => auth.hasRole(['ADMIN', 'OPERATOR']))
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
function canUseXiaohongshuMcp(account?: PlatformAccount): boolean {
  return Boolean(
    account?.localPublishingEnabled &&
    account.availablePublishModes.includes('MCP_PUBLISH') &&
    account.publishMode === 'MCP_PUBLISH' &&
    account.status === 'CONNECTED',
  )
}
function canUseXApi(account?: PlatformAccount): boolean {
  return Boolean(
    account?.status === 'CONNECTED' &&
    account.availablePublishModes.includes('REAL_API') &&
    account.publicPublishEnabled,
  )
}
function defaultPublishMode(platform: Platform, account?: PlatformAccount): PublishMode {
  if (platform === 'XIAOHONGSHU') {
    return canUseXiaohongshuMcp(account) ? 'MCP_PUBLISH' : 'MANUAL_CONFIRM'
  }
  if (platform === 'X') return 'REAL_API'
  return platform === 'WECHAT_OFFICIAL' ? 'DRAFT_ONLY' : 'REAL_API'
}
const publishModes = computed<Array<{ value: PublishMode; label: string; disabled?: boolean }>>(
  () => {
    const account = selectedAccount.value
    if (form.value.platform === 'XIAOHONGSHU')
      return [
        { value: 'MANUAL_CONFIRM', label: '人工发布后确认（默认）' },
        ...(account?.localPublishingEnabled
          ? [
              {
                value: 'MCP_PUBLISH' as PublishMode,
                label: '本机自动发布（仅自己可见）',
                disabled: !canUseXiaohongshuMcp(account),
              },
            ]
          : []),
      ]
    if (form.value.platform === 'WECHAT_OFFICIAL')
      return [
        { value: 'DRAFT_ONLY', label: '自动进入草稿箱', disabled: account?.status !== 'CONNECTED' },
        {
          value: 'REAL_API',
          label: '提交发布',
          disabled: account?.status !== 'CONNECTED' || account.publishMode !== 'SUBMIT_PUBLISH',
        },
      ]
    if (form.value.platform === 'X')
      return [
        {
          value: 'REAL_API',
          label: 'X 官方 API（真实发布）',
          disabled: !canUseXApi(account),
        },
      ]
    return [{ value: 'REAL_API', label: '微博官方 API', disabled: account?.status !== 'CONNECTED' }]
  },
)
const publishModeNames: Record<PublishMode, string> = {
  REAL_API: '官方 API 发布',
  DRAFT_ONLY: '同步到草稿箱',
  SUBMIT_PUBLISH: '提交平台发布',
  MANUAL_CONFIRM: '人工发布确认',
  CDP_PUBLISH: '浏览器自动发布',
  MCP_PUBLISH: '本机自动发布',
  WECHATSYNC_CLI: 'Wechatsync CLI',
}
const accountStatusNames: Record<string, string> = {
  NOT_CONFIGURED: '未配置',
  CONNECTING: '待授权验证',
  CONNECTED: '已连接',
  TOKEN_EXPIRED: '授权已过期',
  INVALID: '连接无效',
  DISABLED: '已停用',
  MANUAL_ONLY: '仅人工交付',
  READY: '已就绪',
  LOGIN_REQUIRED: '需要登录',
}
function publishModeLabel(platform: Platform, mode: PublishMode): string {
  if (platform === 'WEIBO' && mode === 'REAL_API') return '微博官方 API'
  if (platform === 'X' && mode === 'REAL_API') return 'X 官方 API（真实发布）'
  return publishModeNames[mode] || mode
}
const platformGlyphs: Record<Platform, string> = {
  WEIBO: '微',
  XIAOHONGSHU: '红',
  WECHAT_OFFICIAL: '公',
  X: 'X',
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
const events = computed(() =>
  schedules.value
    .filter((x) => !platformFilter.value || x.platform === platformFilter.value)
    .map((x) => ({
      id: String(x.id),
      title: `${platformGlyphs[x.platform]}  ${x.articleTitle}`,
      start: x.scheduledAt,
      backgroundColor: platformColors[x.platform],
      borderColor: platformColors[x.platform],
      classNames: [`platform-${x.platform.toLowerCase()}`],
      extendedProps: x,
    })),
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
      await workflowApi.updateSchedule(Number(info.event.id), {
        scheduled_at: formatLocalDateTime(info.event.start),
      })
      await load()
      ElMessage.success('排期时间已更新')
    } catch (e) {
      info.revert()
      ElMessage.error(getApiErrorMessage(e))
    }
  },
  eventClick: async (info: any) => {
    editing.value = await workflowApi.schedule(Number(info.event.id))
    drawer.value = true
  },
}))
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
function formatLocalDateTime(value: Date): string {
  const offset = value.getTimezoneOffset() * 60_000
  return new Date(value.getTime() - offset).toISOString().slice(0, 19)
}
async function init() {
  const [data, accountRows] = await Promise.all([
    workflowApi.articles({ page_size: 100 }),
    workflowApi.platformAccounts(),
  ])
  articles.value = data.items
  accounts.value = accountRows
  await load()
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
}
function openCreate() {
  form.value = {
    platform: 'WEIBO',
    scheduled_at: formatLocalDateTime(new Date(Date.now() + 3600000)).slice(0, 16),
    publish_mode: 'REAL_API',
  }
  dialog.value = true
}
async function openBacklog(item: ScheduleBacklogItem, date?: Date) {
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
  choosePlatform()
  dialog.value = true
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
            class="!w-full" /></el-form-item
        ><el-form-item
          label="平台账号"
          :required="form.platform !== 'XIAOHONGSHU' || form.publish_mode === 'MCP_PUBLISH'"
          ><el-select v-model="form.account_id" class="w-full" placeholder="请选择平台账号"
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
      </el-form>
      <template #footer>
        <el-button @click="dialog = false">取消</el-button>
        <el-button type="primary" @click="create">创建排期</el-button>
      </template>
    </el-dialog>
  </div>
</template>
