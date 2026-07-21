<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Beaker, Play, Plus, Square } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import EmptyState from '@/components/EmptyState.vue'
import StatusBadge from '@/components/StatusBadge.vue'
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
      <Beaker :size="16" /><span>实验结果只统计实际关联或手工录入的样本，不自动填充示例结论。</span>
    </div>
    <section class="mt-4 grid gap-4 xl:grid-cols-2">
      <article v-for="row in rows" :key="row.id" class="experiment-card panel">
        <div class="flex items-start justify-between">
          <div>
            <p class="section-label">{{ row.type }}</p>
            <button
              class="mt-2 text-left text-lg font-semibold text-ink hover:text-brand"
              @click="open(row)"
            >
              {{ row.name }}
            </button>
          </div>
          <StatusBadge :status="row.status" />
        </div>
        <p class="mt-4 min-h-12 text-sm leading-6 text-muted">{{ row.hypothesis }}</p>
        <div class="mt-5 grid grid-cols-2 gap-3">
          <div class="comparison-cell">
            <small>对照组</small>
            <p>{{ row.controlDescription || '未设置' }}</p>
          </div>
          <div class="comparison-cell accent">
            <small>实验组</small>
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
              v-if="row.status === 'RUNNING'"
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
            <StatusBadge :status="detail.status" />
            <h3 class="mt-3 text-xl font-semibold">{{ detail.name }}</h3>
            <p class="mt-2 text-sm leading-6 text-muted">{{ detail.hypothesis }}</p>
          </div>
          <div class="grid grid-cols-2 gap-3">
            <div class="comparison-cell">
              <small>对照组</small>
              <p>{{ detail.controlDescription }}</p>
            </div>
            <div class="comparison-cell accent">
              <small>实验组</small>
              <p>{{ detail.treatmentDescription }}</p>
            </div>
          </div>
          <div>
            <p class="section-label">样本（{{ detail.samples?.length || 0 }}）</p>
            <div class="mt-3 max-h-80 divide-y divide-line overflow-auto">
              <div v-for="sample in detail.samples" :key="sample.id" class="py-3">
                <div class="flex justify-between">
                  <span class="text-sm font-medium">{{ sample.sampleLabel }}</span
                  ><span class="meta-chip">{{ sample.groupType }}</span>
                </div>
                <p class="mt-1 text-xs text-muted">{{ sample.metricValueJson }}</p>
              </div>
            </div>
          </div>
          <div v-if="detail.result">
            <p class="section-label">统计结果</p>
            <pre class="result-box">{{ JSON.stringify(detail.result, null, 2) }}</pre>
          </div>
        </div></template
      ></el-drawer
    >
  </div>
</template>
