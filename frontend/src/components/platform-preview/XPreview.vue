<script setup lang="ts">
import { computed } from 'vue'
import { BarChart3, Heart, MessageCircle, Repeat2, Share, X as CloseIcon } from 'lucide-vue-next'
import PlatformIcon from '@/components/PlatformIcon.vue'
import type { MediaAsset } from '@/types/business'

const props = defineProps<{
  accountName: string
  contentHtml: string
  tags: string[]
  media: MediaAsset[]
  statusLength: number
  removingId?: number
}>()
const emit = defineEmits<{ remove: [item: MediaAsset] }>()

const visibleMedia = computed(() => props.media.slice(0, 4))
const normalizedTags = computed(() =>
  props.tags
    .map((tag) => tag.replace(/#/g, '').trim())
    .filter(Boolean)
    .map((tag) => `#${tag}`),
)
</script>

<template>
  <article class="x-post-card" data-testid="x-platform-preview">
    <header>
      <span class="x-account-avatar"><PlatformIcon platform="X" size="sm" /></span>
      <div>
        <strong>{{ accountName }}</strong>
        <small>@{{ accountName.replace(/\s+/g, '').toLowerCase() || 'contentpilot' }} · 刚刚</small>
      </div>
      <b aria-label="X">X</b>
    </header>

    <section class="x-post-copy">
      <!-- contentHtml is escaped and produced by StudioPage's restricted renderer. -->
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div v-html="contentHtml" />
      <p v-if="normalizedTags.length">{{ normalizedTags.join(' ') }}</p>
      <small :class="{ warning: statusLength > 280 }">
        {{ statusLength }} / 280 字符（本地估算，最终以后端 / X 校验为准）
      </small>
    </section>

    <p v-if="visibleMedia.length" class="x-media-warning">
      当前 X 自动发布仅发送文字，所选图片不会上传。
    </p>
    <section
      v-if="visibleMedia.length"
      class="x-post-media"
      :class="`count-${visibleMedia.length}`"
    >
      <figure v-for="item in visibleMedia" :key="item.id">
        <img :src="item.thumbnailUrl || item.imageUrl" :alt="item.altText || 'X 帖子配图'" />
        <button
          type="button"
          aria-label="移除图片"
          :disabled="removingId === item.id"
          @click="emit('remove', item)"
        >
          <CloseIcon :size="13" />
        </button>
      </figure>
    </section>

    <footer aria-label="X 帖子互动预览">
      <span><MessageCircle :size="15" />回复</span>
      <span><Repeat2 :size="15" />转帖</span>
      <span><Heart :size="15" />喜欢</span>
      <span><BarChart3 :size="15" />查看</span>
      <span><Share :size="15" />分享</span>
    </footer>
  </article>
</template>

<style scoped>
.x-post-card {
  overflow: hidden;
  border: 1px solid #e5e7eb;
  border-radius: 16px;
  background: #fff;
  color: #0f1419;
}
header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 10px;
  align-items: center;
  padding: 14px 14px 4px;
}
header div {
  min-width: 0;
}
header strong,
header small {
  display: block;
}
header strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
header small {
  margin-top: 1px;
  overflow: hidden;
  color: #536471;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
header > b {
  font-size: 16px;
}
.x-account-avatar {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 50%;
  background: #f1f5f9;
}
.x-post-copy {
  padding: 7px 14px 10px 58px;
  font-size: 13px;
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-word;
}
.x-post-copy :deep(p) {
  margin: 0 0 7px;
}
.x-post-copy > p {
  margin-top: 8px;
  color: #1d9bf0;
}
.x-post-copy > small {
  display: block;
  margin-top: 8px;
  color: #536471;
  font-size: 10px;
}
.x-post-copy > small.warning {
  color: #dc2626;
}
.x-media-warning {
  margin: 0 14px 9px 58px;
  border-radius: 8px;
  background: #fff7ed;
  padding: 7px 9px;
  color: #9a3412;
  font-size: 10px;
  line-height: 1.45;
}
.x-post-media {
  display: grid;
  gap: 2px;
  margin: 0 14px 12px 58px;
  overflow: hidden;
  border-radius: 12px;
}
.x-post-media.count-2,
.x-post-media.count-3,
.x-post-media.count-4 {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.x-post-media figure {
  position: relative;
  min-height: 110px;
  background: #f1f5f9;
}
.x-post-media img {
  width: 100%;
  height: 100%;
  min-height: 110px;
  max-height: 220px;
  object-fit: cover;
}
.x-post-media button {
  position: absolute;
  top: 6px;
  right: 6px;
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border-radius: 50%;
  background: rgb(15 20 25 / 72%);
  color: #fff;
}
footer {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  margin-left: 48px;
  padding: 8px 12px 12px;
  color: #536471;
}
footer span {
  display: flex;
  gap: 3px;
  align-items: center;
  justify-content: center;
  font-size: 10px;
}
</style>
