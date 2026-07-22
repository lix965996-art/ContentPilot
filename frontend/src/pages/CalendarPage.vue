<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import FullCalendar from '@fullcalendar/vue3'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import listPlugin from '@fullcalendar/list'
import interactionPlugin from '@fullcalendar/interaction'
import zhCnLocale from '@fullcalendar/core/locales/zh-cn'
import { ElMessage } from 'element-plus'
import { Plus } from 'lucide-vue-next'
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
  Variant,
} from '@/types/business'
import { platformColors, platformNames } from '@/types/business'
import { useAuthStore } from '@/stores/auth'

const schedules = ref<Schedule[]>([])
const auth = useAuthStore()
const canOperate = computed(() => auth.hasRole(['ADMIN', 'OPERATOR']))
const platformFilter = ref<Platform | ''>('')
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
}>({ platform: 'WEIBO', scheduled_at: '', publish_mode: 'MOCK' })
const availableAccounts = computed(() =>
  accounts.value.filter((item) => item.platform === form.value.platform && item.id),
)
const selectedAccount = computed(() =>
  availableAccounts.value.find((item) => item.id === form.value.account_id),
)
const publishModes = computed<Array<{ value: PublishMode; label: string; disabled?: boolean }>>(
  () => {
    const account = selectedAccount.value
    if (form.value.platform === 'XIAOHONGSHU')
      return [
        { value: 'MANUAL_CONFIRM', label: '人工确认发布' },
        { value: 'MOCK', label: 'Mock 演示' },
      ]
    if (form.value.platform === 'WECHAT_OFFICIAL')
      return [
        { value: 'DRAFT_ONLY', label: '自动进入草稿箱', disabled: account?.status !== 'CONNECTED' },
        {
          value: 'REAL_API',
          label: '提交发布',
          disabled: account?.status !== 'CONNECTED' || account.publishMode !== 'SUBMIT_PUBLISH',
        },
        { value: 'MOCK', label: 'Mock 草稿箱' },
      ]
    return [
      { value: 'REAL_API', label: '官方 API', disabled: account?.status !== 'CONNECTED' },
      { value: 'MOCK', label: 'Mock 演示' },
      { value: 'MANUAL_CONFIRM', label: '人工确认' },
    ]
  },
)
const platformGlyphs: Record<Platform, string> = {
  WEIBO: '微',
  XIAOHONGSHU: '红',
  WECHAT_OFFICIAL: '公',
}
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
  schedules.value = await workflowApi.schedules()
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
}
async function chooseArticle() {
  if (!form.value.article_id) return
  variants.value = await workflowApi.variants(form.value.article_id)
  const first = variants.value[0]
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
  form.value.publish_mode =
    form.value.platform === 'XIAOHONGSHU'
      ? 'MANUAL_CONFIRM'
      : form.value.platform === 'WECHAT_OFFICIAL'
        ? account?.status === 'CONNECTED'
          ? 'DRAFT_ONLY'
          : 'MOCK'
        : account?.status === 'CONNECTED' && account.publishMode === 'REAL_API'
          ? 'REAL_API'
          : 'MOCK'
}
function openCreate() {
  form.value = {
    platform: 'WEIBO',
    scheduled_at: formatLocalDateTime(new Date(Date.now() + 3600000)).slice(0, 16),
    publish_mode: 'MOCK',
  }
  dialog.value = true
}
async function create() {
  try {
    if (!form.value.account_id) {
      ElMessage.warning('请先在“平台账号”页面配置并选择账号')
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
</script>
<template>
  <div>
    <PageHeader title="排期日历" description="查看多平台发布计划，拖拽即可调整发布时间。"
      ><el-button v-if="canOperate" type="primary" @click="openCreate"
        ><Plus :size="16" class="mr-2" />新建排期</el-button
      ></PageHeader
    >
    <section class="calendar-workspace">
      <div class="calendar-filter">
        <span>平台</span
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
            <p class="mt-2">{{ editing.publishMode }}</p>
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
              :label="`${platformNames[item.platform]} · v${item.versionNo} · ${item.title}`"
              :value="item.id" /></el-select></el-form-item
        ><el-form-item label="排期时间" required
          ><el-date-picker
            v-model="form.scheduled_at"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm"
            class="!w-full" /></el-form-item
        ><el-form-item label="平台账号" required
          ><el-select v-model="form.account_id" class="w-full" placeholder="请选择平台账号"
            ><el-option
              v-for="account in availableAccounts"
              :key="account.id || account.platform"
              :label="`${account.accountName} · ${account.status}`"
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
          title="小红书当前采用人工确认发布，不属于服务器无人值守自动发布。"
          type="warning"
          :closable="false"
        />
        ></el-form
      ><template #footer
        ><el-button @click="dialog = false">取消</el-button
        ><el-button type="primary" @click="create">创建排期</el-button></template
      ></el-dialog
    >
  </div>
</template>
