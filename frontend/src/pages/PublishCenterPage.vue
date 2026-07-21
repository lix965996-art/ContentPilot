<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { RefreshCw, Rocket, ScrollText } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
import type { Schedule } from '@/types/business'
import { platformNames } from '@/types/business'
import type { Platform } from '@/types/business'
const rows = ref<Schedule[]>([])
const loading = ref(false)
const detail = ref<Schedule>()
const drawer = ref(false)
const status = ref('')
async function load() {
  loading.value = true
  try {
    rows.value = await workflowApi.schedules(status.value ? { status: status.value } : {})
  } finally {
    loading.value = false
  }
}
async function open(row: Schedule) {
  detail.value = await workflowApi.schedule(row.id)
  drawer.value = true
}
async function action(row: Schedule, name: string) {
  try {
    if (name === 'publish-now')
      await ElMessageBox.confirm('将立即执行当前发布适配器，是否继续？', '立即发布')
    await workflowApi.scheduleAction(
      row.id,
      name,
      name === 'manual-confirm' ? { publishedUrl: 'manual://confirmed' } : {},
    )
    ElMessage.success('操作成功')
    await load()
    if (drawer.value) await open(row)
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(getApiErrorMessage(e))
  }
}
onMounted(load)
function platformLabel(value: string): string {
  return platformNames[value as Platform] || value
}
</script>
<template>
  <div>
    <PageHeader title="发布中心" description="跟踪排期执行、人工确认、失败重试和逐步日志。"
      ><el-button :loading="loading" @click="load"
        ><RefreshCw :size="15" class="mr-2" />刷新</el-button
      ></PageHeader
    >
    <section class="toolbar panel">
      <el-select v-model="status" clearable placeholder="全部状态" class="!w-48" @change="load"
        ><el-option
          v-for="item in [
            'PENDING',
            'RUNNING',
            'MOCK_SUCCESS',
            'WAITING_MANUAL_CONFIRM',
            'FAILED',
            'CANCELLED',
          ]"
          :key="item"
          :label="item"
          :value="item" /></el-select
      ><span class="ml-auto meta-chip">默认人工确认发布</span>
    </section>
    <section class="mt-4 overflow-hidden rounded-xl border border-line bg-white">
      <el-table v-loading="loading" :data="rows"
        ><el-table-column label="任务 / 内容" min-width="310"
          ><template #default="{ row }"
            ><button class="text-left" @click="open(row)">
              <span class="block text-xs text-muted"
                >#{{ row.id }} · {{ platformLabel(row.platform) }}</span
              ><span class="mt-1 block font-medium text-ink">{{ row.articleTitle }}</span>
            </button></template
          ></el-table-column
        ><el-table-column label="计划时间" width="175"
          ><template #default="{ row }">{{
            new Date(row.scheduledAt).toLocaleString('zh-CN', {
              month: '2-digit',
              day: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
            })
          }}</template></el-table-column
        ><el-table-column label="方式" prop="publishMode" width="100" /><el-table-column
          label="状态"
          width="155"
          ><template #default="{ row }"
            ><StatusBadge :status="row.status" /></template></el-table-column
        ><el-table-column label="重试" width="80"
          ><template #default="{ row }">{{ row.retryCount }}/3</template></el-table-column
        ><el-table-column label="操作" width="230"
          ><template #default="{ row }"
            ><el-button
              v-if="row.status === 'PENDING'"
              link
              type="primary"
              @click="action(row, 'publish-now')"
              ><Rocket :size="14" class="mr-1" />立即发布</el-button
            ><el-button
              v-if="row.status === 'FAILED'"
              link
              type="danger"
              @click="action(row, 'retry')"
              >重试</el-button
            ><el-button
              v-if="row.status === 'WAITING_MANUAL_CONFIRM'"
              link
              type="success"
              @click="action(row, 'manual-confirm')"
              >确认完成</el-button
            ><el-button link @click="open(row)"
              ><ScrollText :size="14" class="mr-1" />日志</el-button
            ></template
          ></el-table-column
        ></el-table
      >
    </section>
    <el-drawer v-model="drawer" title="发布任务详情" size="480px"
      ><template v-if="detail"
        ><div class="space-y-5">
          <div class="flex items-start justify-between">
            <div>
              <p class="text-xs text-muted">任务 #{{ detail.id }}</p>
              <h3 class="mt-1 text-lg font-semibold">{{ detail.articleTitle }}</h3>
            </div>
            <StatusBadge :status="detail.status" />
          </div>
          <dl class="info-list">
            <div>
              <dt>平台</dt>
              <dd>{{ platformLabel(detail.platform) }}</dd>
            </div>
            <div>
              <dt>方式</dt>
              <dd>{{ detail.publishMode }}</dd>
            </div>
            <div>
              <dt>计划时间</dt>
              <dd>{{ new Date(detail.scheduledAt).toLocaleString('zh-CN') }}</dd>
            </div>
            <div>
              <dt>发布链接</dt>
              <dd class="break-all">{{ detail.publishedUrl || '—' }}</dd>
            </div>
          </dl>
          <div>
            <p class="section-label">执行日志</p>
            <div v-if="detail.logs?.length" class="timeline mt-3">
              <div v-for="(log, index) in detail.logs" :key="index">
                <i />
                <div>
                  <p class="font-medium">{{ log.step }} · {{ log.status }}</p>
                  <p class="mt-1 text-xs text-muted">
                    {{ log.responseSummary || log.errorMessage }}
                  </p>
                </div>
              </div>
            </div>
            <div v-else class="mt-3 text-sm text-muted">任务尚未产生执行日志。</div>
          </div>
        </div></template
      ></el-drawer
    >
  </div>
</template>
