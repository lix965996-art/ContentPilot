<script setup lang="ts">
import { computed } from 'vue'
import DetailDrawer from '@/components/DetailDrawer.vue'
import type { SimilarHistoryItem } from '@/types/business'

const props = defineProps<{
  modelValue: boolean
  title?: string
  items?: SimilarHistoryItem[]
  retrievalProvider?: string
  embeddingModel?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [value: boolean] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const rows = computed(() => props.items || [])
const selectedCount = computed(() => rows.value.filter((item) => item.selected).length)

const providerLabels: Record<string, string> = {
  LLM_RERANK: 'FAISS 粗检索 + LLM 精排',
  VECTOR_ONLY: '仅向量检索（LLM 不可用）',
  NO_HISTORY: '该平台账号暂无历史内容，也没有可借用的公开数据集',
  NO_VECTOR: '历史内容尚未生成向量',
  UNAVAILABLE: '检索阶段异常，已降级',
}

function formatTime(value?: string | null) {
  if (!value) return '—'
  return new Date(value).toLocaleString('zh-CN', {
    year: '2-digit',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  })
}
</script>

<template>
  <DetailDrawer v-model="visible" :title="title || '相似历史内容'" size="560px">
    <p class="retrieval-note">
      {{ providerLabels[retrievalProvider || ''] || retrievalProvider || '未执行语义检索' }}
      <template v-if="embeddingModel"> · 向量模型 {{ embeddingModel }}</template>
      · 命中 {{ rows.length }} 篇，入选 {{ selectedCount }} 篇
    </p>

    <ol v-if="rows.length" class="history-list">
      <li v-for="item in rows" :key="`${item.refType}-${item.historicalContentId}`">
        <header>
          <strong>{{ item.title || `#${item.historicalContentId}` }}</strong>
          <span v-if="item.crossPlatform" class="badge proxy">
            {{ item.platform }} 跨平台代理
          </span>
          <span class="badge" :class="{ on: item.selected }">{{
            item.selected ? '已采用' : '未采用'
          }}</span>
        </header>
        <p class="excerpt">{{ item.excerpt || '—' }}</p>
        <div class="metrics">
          <span>来源：{{ item.refType === 'HISTORY' ? '历史互动数据' : '系统文章' }}</span>
          <span>发布：{{ formatTime(item.publishTime) }}</span>
          <span>向量相似度：{{ item.vectorSimilarity }}</span>
          <span>
            LLM 相关性：{{ item.llmRelevance === null ? '未评分' : `${item.llmRelevance}/100` }}
          </span>
          <span>综合得分：{{ item.combinedScore }}</span>
        </div>
        <p class="reason">{{ item.selectionReason }}</p>
      </li>
    </ol>
    <p v-else class="empty">该平台账号还没有可用于语义检索的历史内容。</p>
  </DetailDrawer>
</template>

<style scoped>
.retrieval-note {
  margin: 0 0 12px;
  color: var(--sf-muted, #667085);
  font-size: 12px;
  line-height: 1.6;
}
.history-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 10px;
}
.history-list li {
  border: 1px solid var(--sf-line, #e5e7eb);
  border-radius: 8px;
  padding: 10px 12px;
  background: #fff;
}
.history-list header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.history-list strong {
  color: var(--sf-ink, #172033);
  font-size: 13px;
}
.badge {
  border-radius: 999px;
  background: #f2f4f7;
  color: var(--sf-muted, #667085);
  padding: 2px 8px;
  font-size: 11px;
  white-space: nowrap;
}
.badge.on {
  background: #ecfdf3;
  color: #027a48;
}
.badge.proxy {
  background: #fffaeb;
  color: #b54708;
}
.excerpt {
  margin: 6px 0;
  color: var(--sf-muted, #667085);
  font-size: 12px;
  line-height: 1.6;
}
.metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 12px;
  color: var(--sf-muted, #667085);
  font-size: 11px;
}
.reason {
  margin: 6px 0 0;
  color: var(--sf-ink, #172033);
  font-size: 12px;
  line-height: 1.6;
}
.empty {
  color: var(--sf-muted, #667085);
  font-size: 12px;
}
</style>
