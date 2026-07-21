<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { FilePlus2, FileText, MoreHorizontal, PenLine, Search, Upload } from 'lucide-vue-next'
import { useRouter } from 'vue-router'
import { apiClient, getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import EmptyState from '@/components/EmptyState.vue'
import FilterBar from '@/components/FilterBar.vue'
import PageHeader from '@/components/PageHeader.vue'
import PlatformIcon from '@/components/PlatformIcon.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { useAuthStore } from '@/stores/auth'
import type { Article, Platform } from '@/types/business'

const router = useRouter()
const auth = useAuthStore()
const canOperate = computed(() => auth.hasRole(['ADMIN', 'OPERATOR']))
const rows = ref<Article[]>([])
const total = ref(0)
const loading = ref(false)
const importing = ref(false)
const editorOpen = ref(false)
const editingId = ref<number>()
const rowPlatforms = ref<Record<number, Platform[]>>({})
const filters = reactive({ keyword: '', status: '', platform: '' })
const tabs = [
  ['全部', ''],
  ['草稿', 'DRAFT'],
  ['待审核', 'GENERATED'],
  ['已通过', 'APPROVED'],
  ['已排期', 'SCHEDULED'],
  ['已发布', 'PUBLISHED'],
  ['已归档', 'ARCHIVED'],
]
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
    const pairs = await Promise.all(
      data.items.map(
        async (row) =>
          [
            row.id,
            [...new Set((await workflowApi.variants(row.id)).map((x) => x.platform))],
          ] as const,
      ),
    )
    const mapping: Record<number, Platform[]> = {}
    for (const [id, platforms] of pairs) mapping[id] = [...platforms]
    rowPlatforms.value = mapping
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
    ElMessage.success('内容已保存')
    editorOpen.value = false
    await load()
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error))
  }
}
async function remove(row: Article) {
  await ElMessageBox.confirm(`确认删除《${row.title}》？`, '删除内容', { type: 'warning' })
  await workflowApi.deleteArticle(row.id)
  await load()
}
async function archive(row: Article) {
  await workflowApi.archiveArticle(row.id)
  await load()
}
function toStudio(row: Article) {
  router.push({ name: 'studio', query: { article: row.id } })
}
function selectStatus(value: string) {
  filters.status = value
  void load()
}
onMounted(load)
</script>

<template>
  <div>
    <PageHeader title="内容库" description="统一管理原文、平台版本和审核进度。">
      <el-upload
        v-if="canOperate"
        :show-file-list="false"
        :http-request="importArticle"
        accept=".txt,.md,.markdown"
        ><el-button :loading="importing"
          ><Upload :size="15" class="mr-2" />导入</el-button
        ></el-upload
      >
      <el-button v-if="canOperate" type="primary" @click="openCreate"
        ><FilePlus2 :size="15" class="mr-2" />新建内容</el-button
      >
    </PageHeader>
    <div class="content-tabs">
      <button
        v-for="tab in tabs"
        :key="tab[0]"
        :class="{ active: filters.status === tab[1] }"
        @click="selectStatus(tab[1])"
      >
        {{ tab[0] }}
      </button>
    </div>
    <FilterBar>
      <el-input
        v-model="filters.keyword"
        clearable
        placeholder="搜索标题或正文"
        class="!w-64"
        @keyup.enter="load"
        ><template #prefix><Search :size="15" /></template
      ></el-input>
      <el-select
        v-model="filters.platform"
        clearable
        placeholder="全部平台"
        class="!w-36"
        @change="load"
        ><el-option label="微博" value="WEIBO" /><el-option
          label="小红书"
          value="XIAOHONGSHU" /><el-option label="微信公众号" value="WECHAT_OFFICIAL"
      /></el-select>
      <el-select placeholder="全部主题" class="!w-32" disabled />
      <el-date-picker
        type="daterange"
        range-separator="至"
        start-placeholder="开始日期"
        end-placeholder="结束日期"
        class="!w-64"
        disabled
      />
      <span class="ml-auto text-xs text-muted">{{ total }} 条内容</span>
    </FilterBar>
    <section v-loading="loading" class="content-list mt-3">
      <article v-for="row in rows" :key="row.id" class="content-row">
        <button class="content-thumb" @click="openEdit(row)"><FileText :size="20" /></button>
        <button class="content-summary" @click="openEdit(row)">
          <strong>{{ row.title }}</strong
          ><span>{{ row.summary || row.sourceText }}</span
          ><small>{{ row.topic || '未分类' }} · {{ row.variantCount }} 个平台版本</small>
        </button>
        <div class="content-platforms">
          <PlatformIcon
            v-for="item in rowPlatforms[row.id]"
            :key="item"
            :platform="item"
            size="sm"
          /><span v-if="!rowPlatforms[row.id]?.length">—</span>
        </div>
        <StatusBadge :status="row.status" />
        <time>{{
          new Date(row.updatedAt).toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
          })
        }}</time>
        <div v-if="canOperate" class="row-actions">
          <el-tooltip content="继续编辑"
            ><button @click="toStudio(row)"><PenLine :size="15" /></button></el-tooltip
          ><el-dropdown trigger="click"
            ><button><MoreHorizontal :size="17" /></button
            ><template #dropdown
              ><el-dropdown-menu
                ><el-dropdown-item @click="openEdit(row)">编辑原文</el-dropdown-item
                ><el-dropdown-item @click="toStudio(row)">生成平台版本</el-dropdown-item
                ><el-dropdown-item @click="archive(row)">归档</el-dropdown-item
                ><el-dropdown-item divided @click="remove(row)"
                  >删除</el-dropdown-item
                ></el-dropdown-menu
              ></template
            ></el-dropdown
          >
        </div>
      </article>
      <EmptyState
        v-if="!loading && !rows.length"
        title="内容库还是空的"
        description="创建第一篇原文，或导入已有的 Markdown 文稿。"
        ><template #icon><FilePlus2 :size="28" /></template
        ><el-button v-if="canOperate" type="primary" plain @click="openCreate"
          >新建内容</el-button
        ></EmptyState
      >
    </section>
    <el-dialog
      v-model="editorOpen"
      :title="editingId ? '编辑原文' : '新建内容'"
      width="min(820px, 92vw)"
      destroy-on-close
    >
      <el-form label-position="top"
        ><div class="grid gap-x-4 sm:grid-cols-2">
          <el-form-item label="标题" class="sm:col-span-2" required
            ><el-input v-model="form.title" maxlength="255" show-word-limit
          /></el-form-item>
          <el-form-item label="主题"
            ><el-input v-model="form.topic" placeholder="例如：校园运营" /></el-form-item
          ><el-form-item label="目标受众"><el-input v-model="form.target_audience" /></el-form-item>
          <el-form-item label="语气"
            ><el-select v-model="form.tone" class="w-full"
              ><el-option label="专业自然" value="专业自然" /><el-option
                label="轻松亲切"
                value="轻松亲切" /><el-option label="理性克制" value="理性克制" /></el-select
          ></el-form-item>
          <el-form-item label="关键词"
            ><el-select v-model="form.keywords" multiple allow-create filterable class="w-full"
          /></el-form-item>
          <el-form-item label="摘要" class="sm:col-span-2"
            ><el-input v-model="form.summary" type="textarea" :rows="2"
          /></el-form-item>
          <el-form-item label="原文正文" class="sm:col-span-2" required
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
        ><el-button type="primary" @click="save">保存内容</el-button></template
      >
    </el-dialog>
  </div>
</template>
