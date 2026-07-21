<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Archive, FilePlus2, Search, PenLine, Upload } from 'lucide-vue-next'
import { useRouter } from 'vue-router'

import { apiClient, getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import PageHeader from '@/components/PageHeader.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import type { Article } from '@/types/business'

const router = useRouter()
const rows = ref<Article[]>([])
const total = ref(0)
const loading = ref(false)
const importing = ref(false)
const editorOpen = ref(false)
const editingId = ref<number>()
const filters = reactive({ keyword: '', status: '' })
const form = reactive({
  title: '',
  source_text: '',
  summary: '',
  topic: '',
  target_audience: '校园新媒体运营者',
  tone: '专业自然',
  keywords: [] as string[],
  status: 'DRAFT',
})

async function load() {
  loading.value = true
  try {
    const data = await workflowApi.articles(filters)
    rows.value = data.items
    total.value = data.total
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  } finally {
    loading.value = false
  }
}
async function importArticle(options: any) {
  importing.value = true
  const body = new FormData()
  body.append('file', options.file)
  try {
    await apiClient.post('/articles/import', body, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    ElMessage.success('原文导入成功')
    await load()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '导入失败'))
  } finally {
    importing.value = false
  }
}
function openCreate() {
  editingId.value = undefined
  Object.assign(form, {
    title: '',
    source_text: '',
    summary: '',
    topic: '',
    target_audience: '校园新媒体运营者',
    tone: '专业自然',
    keywords: [],
    status: 'DRAFT',
  })
  editorOpen.value = true
}
async function openEdit(row: Article) {
  const detail = await workflowApi.article(row.id)
  editingId.value = row.id
  Object.assign(form, {
    title: detail.title,
    source_text: detail.sourceText,
    summary: detail.summary || '',
    topic: detail.topic || '',
    target_audience: detail.targetAudience || '',
    tone: detail.tone || '',
    keywords: detail.keywords || [],
    status: detail.status,
  })
  editorOpen.value = true
}
async function save() {
  if (!form.title.trim() || form.source_text.trim().length < 10)
    return ElMessage.warning('请填写标题和至少 10 个字的正文')
  try {
    if (editingId.value) await workflowApi.updateArticle(editingId.value, form)
    else await workflowApi.createArticle(form)
    ElMessage.success('文章已保存')
    editorOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  }
}
async function remove(row: Article) {
  await ElMessageBox.confirm(`确认删除《${row.title}》？`, '删除文章', { type: 'warning' })
  await workflowApi.deleteArticle(row.id)
  ElMessage.success('文章已删除')
  await load()
}
async function archive(row: Article) {
  await workflowApi.archiveArticle(row.id)
  ElMessage.success('文章已归档')
  await load()
}
function toStudio(row: Article) {
  router.push({ name: 'studio', query: { article: row.id } })
}
onMounted(load)
</script>

<template>
  <div>
    <PageHeader title="内容库" description="管理原文、平台版本和审核状态。">
      <el-upload :show-file-list="false" :http-request="importArticle" accept=".txt,.md,.markdown">
        <el-button :loading="importing"><Upload :size="16" class="mr-2" />导入原文</el-button>
      </el-upload>
      <el-button type="primary" @click="openCreate"
        ><FilePlus2 :size="16" class="mr-2" />新建原文</el-button
      >
    </PageHeader>
    <section class="toolbar panel">
      <el-input
        v-model="filters.keyword"
        clearable
        placeholder="搜索标题或正文"
        class="!w-64"
        @keyup.enter="load"
        ><template #prefix><Search :size="15" /></template
      ></el-input>
      <el-select v-model="filters.status" clearable placeholder="全部状态" class="!w-36"
        ><el-option label="草稿" value="DRAFT" /><el-option
          label="已生成"
          value="GENERATED" /><el-option label="已审核" value="APPROVED" /><el-option
          label="已归档"
          value="ARCHIVED"
      /></el-select>
      <el-button @click="load">筛选</el-button
      ><span class="ml-auto text-xs text-muted">共 {{ total }} 篇</span>
    </section>
    <section class="mt-4 overflow-hidden rounded-xl border border-line bg-white">
      <el-table v-loading="loading" :data="rows" row-key="id" class="w-full">
        <el-table-column label="内容" min-width="360"
          ><template #default="{ row }"
            ><button class="text-left" @click="openEdit(row)">
              <span class="block font-medium text-ink hover:text-brand">{{ row.title }}</span
              ><span class="mt-1 block max-w-xl truncate text-xs text-muted">{{
                row.sourceText
              }}</span>
            </button></template
          ></el-table-column
        >
        <el-table-column label="主题" prop="topic" width="130" />
        <el-table-column label="版本" width="90"
          ><template #default="{ row }"
            ><span class="tabular-nums">{{ row.variantCount }}</span></template
          ></el-table-column
        >
        <el-table-column label="状态" width="120"
          ><template #default="{ row }"><StatusBadge :status="row.status" /></template
        ></el-table-column>
        <el-table-column label="更新时间" width="170"
          ><template #default="{ row }">{{
            new Date(row.updatedAt).toLocaleString('zh-CN', {
              month: '2-digit',
              day: '2-digit',
              hour: '2-digit',
              minute: '2-digit',
            })
          }}</template></el-table-column
        >
        <el-table-column label="操作" width="245" fixed="right"
          ><template #default="{ row }"
            ><el-button link type="primary" @click="toStudio(row)"
              ><PenLine :size="14" class="mr-1" />生成平台版本</el-button
            ><el-button link @click="openEdit(row)">编辑</el-button
            ><el-dropdown
              ><el-button link class="ml-3">更多</el-button
              ><template #dropdown
                ><el-dropdown-menu
                  ><el-dropdown-item @click="archive(row)"
                    ><Archive :size="14" class="mr-2" />归档</el-dropdown-item
                  ><el-dropdown-item divided @click="remove(row)"
                    >删除</el-dropdown-item
                  ></el-dropdown-menu
                ></template
              ></el-dropdown
            ></template
          ></el-table-column
        >
        <template #empty
          ><div class="empty-state">
            <FilePlus2 :size="28" />
            <p>还没有原文</p>
            <span>新建一篇内容，开始多平台适配。</span
            ><el-button type="primary" plain @click="openCreate">新建原文</el-button>
          </div></template
        >
      </el-table>
    </section>
    <el-dialog
      v-model="editorOpen"
      :title="editingId ? '编辑原文' : '新建原文'"
      width="min(820px, 92vw)"
      destroy-on-close
    >
      <el-form label-position="top"
        ><div class="grid gap-x-4 sm:grid-cols-2">
          <el-form-item label="标题" class="sm:col-span-2" required
            ><el-input v-model="form.title" maxlength="255" show-word-limit /></el-form-item
          ><el-form-item label="主题"
            ><el-input v-model="form.topic" placeholder="例如：校园运营" /></el-form-item
          ><el-form-item label="目标受众"><el-input v-model="form.target_audience" /></el-form-item
          ><el-form-item label="语气"
            ><el-select v-model="form.tone" class="w-full"
              ><el-option label="专业自然" value="专业自然" /><el-option
                label="轻松亲切"
                value="轻松亲切" /><el-option
                label="理性克制"
                value="理性克制" /></el-select></el-form-item
          ><el-form-item label="关键词"
            ><el-select
              v-model="form.keywords"
              multiple
              allow-create
              filterable
              class="w-full" /></el-form-item
          ><el-form-item label="摘要" class="sm:col-span-2"
            ><el-input v-model="form.summary" type="textarea" :rows="2" /></el-form-item
          ><el-form-item label="原文正文" class="sm:col-span-2" required
            ><el-input
              v-model="form.source_text"
              type="textarea"
              :rows="12"
              maxlength="100000"
              show-word-limit
          /></el-form-item></div
      ></el-form>
      <template #footer
        ><el-button @click="editorOpen = false">取消</el-button
        ><el-button type="primary" @click="save">保存文章</el-button></template
      >
    </el-dialog>
  </div>
</template>
