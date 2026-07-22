<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Beaker, Play, Plus, Square } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import { workflowApi } from '@/api/workflow'
import { getApiErrorMessage } from '@/api/client'
const rows = ref<Array<Record<string, any>>>([])
const dialog = ref(false)
const detail = ref<Record<string, any>>()
const drawer = ref(false)
const form = reactive({
  name: '',
  type: 'PUBLISH_TIME',
  hypothesis: '',
  control_description: '',
  treatment_description: '',
  metrics: {} as Record<string, string>,
})
const controlStats = computed(() => detail.value?.statistics?.CONTROL || {})
const treatmentStats = computed(() => detail.value?.statistics?.TREATMENT || {})
const engagementDifference = computed(
  () =>
    Number(treatmentStats.value.engagementRate || 0) -
    Number(controlStats.value.engagementRate || 0),
)

function typeLabel(value: string) {
  return value === 'PUBLISH_TIME' ? '发布时间对比' : '内容效率对比'
}

function statusLabel(value: string) {
  if (['RUNNING', 'ACTIVE'].includes(value)) return '进行中'
  if (value === 'FINISHED') return '已结束'
  return '未开始'
}

function statusType(value: string) {
  if (['RUNNING', 'ACTIVE'].includes(value)) return 'success'
  if (value === 'FINISHED') return 'info'
  return 'warning'
}

function groupLabel(value: string) {
  return value === 'TREATMENT' ? '推荐时段组' : '常规时段组'
}

function formatPercent(value: unknown) {
  const number = Number(value)
  return Number.isFinite(number) ? `${number.toFixed(2)}%` : '暂无数据'
}

function formatDate(value: unknown) {
  return value ? new Date(String(value)).toLocaleDateString('zh-CN') : '—'
}

function conclusionText() {
  const controlCount = Number(controlStats.value.sampleCount || 0)
  const treatmentCount = Number(treatmentStats.value.sampleCount || 0)
  if (controlCount < 3 || treatmentCount < 3) {
    return '两组样本都不足 3 条，目前只能验证流程，不能据此调整正式发布时间。'
  }
  const difference = engagementDifference.value
  if (Math.abs(difference) < 0.5) return '两组互动率接近，暂未观察到明显差异。'
  return difference > 0
    ? `推荐时段组平均互动率高 ${difference.toFixed(2)} 个百分点。`
    : `推荐时段组平均互动率低 ${Math.abs(difference).toFixed(2)} 个百分点。`
}
async function load() {
  rows.value = await workflowApi.experiments()
}
async function create() {
  try {
    await workflowApi.createExperiment(form)
    dialog.value = false
    ElMessage.success('实验已创建')
    await load()
  } catch (e) {
    ElMessage.error(getApiErrorMessage(e))
  }
}
async function action(row: any, name: string) {
  await workflowApi.experimentAction(row.id, name)
  ElMessage.success(name === 'start' ? '实验已开始' : '实验已完成并汇总')
  await load()
}
async function open(row: any) {
  detail.value = await workflowApi.experiment(row.id)
  drawer.value = true
}
onMounted(load)
</script>
<template>
  <div>
    <PageHeader
      title="实验管理"
      description="管理内容适配效率实验和推荐时间对照实验，保留样本与可复现结果。"
      ><el-button type="primary" @click="dialog = true"
        ><Plus :size="16" class="mr-2" />新建实验</el-button
      ></PageHeader
    >
    <div class="notice-strip">
      <Beaker :size="16" /><span
        >怎么用：把相近内容分别安排在常规时段和推荐时段，导入发布数据后比较两组平均互动率；每组至少
        3 条样本再判断。</span
      >
    </div>
    <section class="mt-4 grid gap-4 xl:grid-cols-2">
      <article v-for="row in rows" :key="row.id" class="experiment-card panel">
        <div class="flex items-start justify-between">
          <div>
            <p class="section-label">{{ typeLabel(row.type) }}</p>
            <button
              class="mt-2 text-left text-lg font-semibold text-ink hover:text-brand"
              @click="open(row)"
            >
              {{ row.name }}
            </button>
          </div>
          <el-tag :type="statusType(row.status)" round>{{ statusLabel(row.status) }}</el-tag>
        </div>
        <p class="mt-4 min-h-12 text-sm leading-6 text-muted">{{ row.hypothesis }}</p>
        <div class="mt-5 grid grid-cols-2 gap-3">
          <div class="comparison-cell">
            <small>常规时段组</small>
            <p>{{ row.controlDescription || '未设置' }}</p>
          </div>
          <div class="comparison-cell accent">
            <small>推荐时段组</small>
            <p>{{ row.treatmentDescription || '未设置' }}</p>
          </div>
        </div>
        <div class="mt-5 flex items-center justify-between border-t border-line pt-4">
          <span class="text-xs text-muted">{{ row.sampleCount }} 个样本</span>
          <div>
            <el-button
              v-if="row.status === 'DRAFT'"
              size="small"
              type="primary"
              plain
              @click="action(row, 'start')"
              ><Play :size="14" class="mr-1" />开始</el-button
            ><el-button
              v-if="['RUNNING', 'ACTIVE'].includes(row.status)"
              size="small"
              type="success"
              plain
              @click="action(row, 'finish')"
              ><Square :size="14" class="mr-1" />结束并统计</el-button
            ><el-button size="small" @click="open(row)">查看</el-button>
          </div>
        </div>
      </article>
      <EmptyState v-if="!rows.length" class="xl:col-span-2" title="还没有实验"
        ><template #icon><Beaker :size="27" /></template
        ><el-button type="primary" plain @click="dialog = true">新建实验</el-button></EmptyState
      >
    </section>
    <el-dialog v-model="dialog" title="新建实验" width="600px"
      ><el-form label-position="top"
        ><el-form-item label="实验名称" required><el-input v-model="form.name" /></el-form-item
        ><el-form-item label="实验类型"
          ><el-radio-group v-model="form.type"
            ><el-radio-button value="CONTENT_EFFICIENCY">内容适配效率</el-radio-button
            ><el-radio-button value="PUBLISH_TIME">发布时间对比</el-radio-button></el-radio-group
          ></el-form-item
        ><el-form-item label="研究假设" required
          ><el-input v-model="form.hypothesis" type="textarea" :rows="3"
        /></el-form-item>
        <div class="grid grid-cols-2 gap-4">
          <el-form-item label="对照组"
            ><el-input v-model="form.control_description" type="textarea" :rows="3" /></el-form-item
          ><el-form-item label="实验组"
            ><el-input v-model="form.treatment_description" type="textarea" :rows="3"
          /></el-form-item></div></el-form
      ><template #footer
        ><el-button @click="dialog = false">取消</el-button
        ><el-button type="primary" @click="create">创建实验</el-button></template
      ></el-dialog
    ><el-drawer v-model="drawer" title="实验详情" size="520px"
      ><template v-if="detail"
        ><div class="space-y-5">
          <div>
            <el-tag :type="statusType(detail.status)" round>{{
              statusLabel(detail.status)
            }}</el-tag>
            <h3 class="mt-3 text-xl font-semibold">{{ detail.name }}</h3>
            <p class="section-label mt-5">这个实验要回答什么</p>
            <p class="mt-2 text-sm leading-6 text-muted">{{ detail.hypothesis }}</p>
            <div
              v-if="detail.hasSimulatedData"
              class="mt-4 rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800"
            >
              当前全部为本地演示数据，只用于说明功能，不能作为真实运营结论。
            </div>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="comparison-cell">
              <small>常规时段组</small>
              <p>{{ detail.controlDescription }}</p>
            </div>
            <div class="comparison-cell accent">
              <small>推荐时段组</small>
              <p>{{ detail.treatmentDescription }}</p>
            </div>
          </div>
          <div>
            <p class="section-label">当前对比</p>
            <div class="mt-3 grid grid-cols-2 gap-3">
              <div class="rounded-xl border border-line p-4">
                <small class="text-muted">常规时段平均互动率</small>
                <strong class="mt-2 block text-2xl">{{
                  formatPercent(controlStats.engagementRate)
                }}</strong>
                <span class="mt-1 block text-xs text-muted"
                  >{{ controlStats.sampleCount || 0 }} 条样本</span
                >
              </div>
              <div class="rounded-xl border border-blue-200 bg-blue-50 p-4">
                <small class="text-blue-700">推荐时段平均互动率</small>
                <strong class="mt-2 block text-2xl text-blue-700">{{
                  formatPercent(treatmentStats.engagementRate)
                }}</strong>
                <span class="mt-1 block text-xs text-blue-600"
                  >{{ treatmentStats.sampleCount || 0 }} 条样本</span
                >
              </div>
            </div>
            <div class="mt-3 rounded-xl bg-surface p-4 text-sm leading-6 text-ink">
              <b>当前判断：</b>{{ conclusionText() }}
            </div>
          </div>
          <div>
            <p class="section-label">样本明细（{{ detail.samples?.length || 0 }}）</p>
            <div class="mt-3 max-h-80 divide-y divide-line overflow-auto">
              <div v-for="(sample, index) in detail.samples" :key="sample.id" class="py-3">
                <div class="flex justify-between">
                  <span class="text-sm font-medium"
                    >{{ groupLabel(sample.groupType) }}样本 {{ index + 1 }}</span
                  ><span class="meta-chip">{{ groupLabel(sample.groupType) }}</span>
                </div>
                <div class="mt-2 flex items-center justify-between text-xs text-muted">
                  <span>互动率 {{ formatPercent(sample.metricValueJson?.engagementRate) }}</span>
                  <span>{{ formatDate(sample.createdAt) }} · 演示数据</span>
                </div>
              </div>
            </div>
          </div>
          <div>
            <p class="section-label">实验结论</p>
            <p class="mt-2 rounded-xl border border-line p-4 text-sm leading-6 text-muted">
              {{ detail.conclusion || conclusionText() }}
            </p>
          </div>
        </div></template
      ></el-drawer
    >
  </div>
</template>
