<script setup lang="ts">
import PlatformIcon from '@/components/PlatformIcon.vue'
import type { MediaAsset } from '@/types/business'

defineProps<{
  accountName: string
  title: string
  contentHtml: string
  tags: string[]
  media: MediaAsset[]
  removingId?: number
}>()
defineEmits<{ remove: [item: MediaAsset]; setCover: [item: MediaAsset] }>()
</script>

<template>
  <article class="toutiao-preview">
    <header>
      <PlatformIcon platform="TOUTIAO" size="sm" />
      <div>
        <b>{{ accountName }}</b
        ><small>头条号文章预览</small>
      </div>
    </header>
    <h2>{{ title || '今日头条文章标题' }}</h2>
    <div v-if="media.length" class="toutiao-cover">
      <img :src="media[0].thumbnailUrl || media[0].imageUrl" :alt="media[0].altText || title" />
      <button
        type="button"
        :disabled="removingId === media[0].id"
        @click="$emit('remove', media[0])"
      >
        移除
      </button>
    </div>
    <!-- contentHtml is sanitized with DOMPurify by StudioPage before it reaches the preview. -->
    <!-- eslint-disable-next-line vue/no-v-html -->
    <div class="toutiao-body" v-html="contentHtml" />
    <footer>
      <span v-for="tag in tags" :key="tag">{{ tag.replace(/^#|#$/g, '') }}</span>
    </footer>
  </article>
</template>

<style scoped>
.toutiao-preview {
  background: #fff;
  border: 1px solid #e5e7eb;
  border-radius: 18px;
  padding: 22px;
  color: #1f2329;
}
header {
  display: flex;
  gap: 10px;
  align-items: center;
}
header div {
  display: grid;
}
header small {
  color: #98a2b3;
  margin-top: 2px;
}
h2 {
  margin: 22px 0 14px;
  font-size: 24px;
  line-height: 1.35;
}
.toutiao-cover {
  position: relative;
  overflow: hidden;
  border-radius: 12px;
  aspect-ratio: 16 / 9;
  background: #f2f4f7;
}
.toutiao-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.toutiao-cover button {
  position: absolute;
  right: 10px;
  top: 10px;
  border: 0;
  border-radius: 8px;
  padding: 5px 9px;
  background: rgba(17, 24, 39, 0.72);
  color: white;
}
.toutiao-body {
  margin-top: 18px;
  line-height: 1.85;
  color: #344054;
  max-height: 420px;
  overflow: auto;
}
footer {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 18px;
}
footer span {
  padding: 4px 9px;
  border-radius: 999px;
  color: #d92d20;
  background: #fff1f0;
  font-size: 12px;
}
</style>
