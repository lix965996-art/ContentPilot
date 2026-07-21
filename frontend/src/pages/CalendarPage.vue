<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import FullCalendar from '@fullcalendar/vue3'
import dayGridPlugin from '@fullcalendar/daygrid'
import timeGridPlugin from '@fullcalendar/timegrid'
import interactionPlugin from '@fullcalendar/interaction'
import zhCnLocale from '@fullcalendar/core/locales/zh-cn'
import { ElMessage } from 'element-plus'
import { Plus } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import type { Article, Platform, Schedule, Variant } from '@/types/business'
import { platformColors, platformNames } from '@/types/business'

const schedules = ref<Schedule[]>([])
const drawer = ref(false)
const editing = ref<Schedule>()
const dialog = ref(false)
const articles = ref<Article[]>([])
const variants = ref<Variant[]>([])
const form = ref<{
  article_id?: number
  variant_id?: number
  platform: Platform
  scheduled_at: string
  publish_mode: string
}>({ platform: 'WEIBO', scheduled_at: '', publish_mode: 'MANUAL' })
const events = computed(() =>
  schedules.value.map((x) => ({
    id: String(x.id),
    title: `${platformNames[x.platform]} · ${x.articleTitle}`,
    start: x.scheduledAt,
    backgroundColor: platformColors[x.platform],
    borderColor: platformColors[x.platform],
    extendedProps: x,
  })),
)
const options = computed(() => ({
  plugins: [dayGridPlugin, timeGridPlugin, interactionPlugin],
  locale: zhCnLocale,
  initialView: 'dayGridMonth',
  headerToolbar: {
    left: 'prev,next today',
    center: 'title',
    right: 'dayGridMonth,timeGridWeek,timeGridDay',
  },
  height: 'auto',
  editable: true,
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
  const data = await workflowApi.articles({ page_size: 100 })
  articles.value = data.items
  await load()
}
async function chooseArticle() {
  if (!form.value.article_id) return
  variants.value = await workflowApi.variants(form.value.article_id)
  const first = variants.value[0]
  if (first) {
    form.value.variant_id = first.id
    form.value.platform = first.platform
  }
}
function chooseVariant(id: number) {
  const item = variants.value.find((x) => x.id === id)
  if (item) form.value.platform = item.platform
}
function openCreate() {
  form.value = {
    platform: 'WEIBO',
    scheduled_at: formatLocalDateTime(new Date(Date.now() + 3600000)).slice(0, 16),
    publish_mode: 'MANUAL',
  }
  dialog.value = true
}
async function create() {
  try {
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
    <PageHeader title="排期日历" description="按月、周、日查看多平台任务，拖拽即可调整发布时间。"
      ><el-button type="primary" @click="openCreate"
        ><Plus :size="16" class="mr-2" />新建排期</el-button
      ></PageHeader
    >
    <section class="calendar-shell panel">
      <FullCalendar :options="{ ...options, events }" />
    </section>
    <el-drawer v-model="drawer" title="排期详情" size="420px"
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
      ></el-drawer
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
        ><el-form-item label="发布方式"
          ><el-radio-group v-model="form.publish_mode"
            ><el-radio-button value="MANUAL">人工确认</el-radio-button
            ><el-radio-button value="MOCK" disabled>演示模式</el-radio-button></el-radio-group
          ></el-form-item
        ></el-form
      ><template #footer
        ><el-button @click="dialog = false">取消</el-button
        ><el-button type="primary" @click="create">创建排期</el-button></template
      ></el-dialog
    >
  </div>
</template>
