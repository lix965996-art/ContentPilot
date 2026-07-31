<script setup lang="ts">
import { computed } from 'vue'
import { X } from 'lucide-vue-next'
import PlatformIcon from '@/components/PlatformIcon.vue'
import type { MediaAsset } from '@/types/business'

const props = defineProps<{
  accountName: string
  title: string
  contentHtml: string
  tags: string[]
  media: MediaAsset[]
  statusLength: number
  removingId?: number
}>()

const emit = defineEmits<{ remove: [item: MediaAsset] }>()

const topics = computed(() =>
  props.tags
    .map((tag) => tag.replace(/#/g, '').trim())
    .filter(Boolean)
    .map((tag) => `#${tag}#`),
)
</script>

<template>
  <article
    class="weibo-card"
    data-testid="weibo-platform-preview"
    :data-status-length="statusLength"
  >
    <header class="account-row">
      <span class="account-avatar"><PlatformIcon platform="WEIBO" size="sm" /></span>
      <div>
        <b>{{ accountName }}</b>
        <span>刚刚 · 来自 ContentPilot</span>
      </div>
      <i>•••</i>
    </header>

    <section class="weibo-copy">
      <strong v-if="title" class="weibo-hook">{{ title }}</strong>
      <!-- contentHtml is escaped and produced by StudioPage's restricted renderer. -->
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div class="weibo-body" v-html="contentHtml" />
      <p v-if="topics.length" class="weibo-topics">{{ topics.join(' ') }}</p>
    </section>

    <p v-if="media.length && statusLength > 140" class="publish-warning">
      当前共 {{ statusLength }} 字；系统会在安排发布时自动压缩为 140 字以内的可发布版本。
    </p>
    <p v-else-if="!media.length && statusLength > 140" class="longtext-note">
      {{ statusLength }} 字 · 将使用微博长文字参数
    </p>
    <div v-if="media.length" class="weibo-media count-1">
      <figure v-for="item in media.slice(0, 1)" :key="item.id">
        <img :src="item.thumbnailUrl || item.imageUrl" :alt="item.altText || '微博配图'" />
        <button
          type="button"
          :disabled="removingId === item.id"
          :aria-label="`移除图片：${item.altText || item.id}`"
          title="移除这张图片"
          @click.stop="emit('remove', item)"
        >
          <X :size="13" />
        </button>
      </figure>
    </div>
    <p v-if="media.length > 1" class="single-image-note">
      微博官方发布适配器仅发送首张图，其余图片仍保留给小红书和公众号使用。
    </p>
    <div v-else class="media-empty">尚未选择图片</div>

    <footer><span>转发</span><span>评论</span><span>赞</span></footer>
  </article>
</template>

<style scoped>
.weibo-card {
  overflow: hidden;
  max-width: 380px;
  margin: 0 auto;
  border: 1px solid #e5e7eb;
  border-radius: 12px;
  background: #fff;
  box-shadow: 0 6px 20px rgba(16, 24, 40, 0.06);
}
.account-row {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 14px 14px 7px;
}
.account-avatar {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border-radius: 50%;
  background: #fff0f2;
}
.account-row div {
  min-width: 0;
  flex: 1;
}
.account-row b,
.account-row span {
  display: block;
}
.account-row b {
  overflow: hidden;
  color: #202124;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.account-row span {
  margin-top: 2px;
  color: #98a2b3;
  font-size: 11px;
}
.account-row i {
  color: #98a2b3;
  font-size: 11px;
  font-style: normal;
}
.weibo-copy {
  padding: 5px 14px 12px;
}
.weibo-hook {
  display: block;
  margin-bottom: 7px;
  color: #1f2329;
  font-size: 13px;
  line-height: 1.65;
}
.weibo-body {
  max-height: 190px;
  overflow: auto;
  color: #344054;
  font-size: 12px;
  line-height: 1.75;
}
.weibo-body :deep(p) {
  margin: 7px 0;
}
.weibo-body :deep(h3),
.weibo-body :deep(h4),
.weibo-body :deep(h5) {
  margin: 10px 0 5px;
  font-size: 12px;
}
.weibo-topics {
  margin: 8px 0 0;
  color: #1677ff;
  font-size: 11px;
  line-height: 1.6;
}
.weibo-media {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 3px;
  padding: 0 14px 13px;
}
.weibo-media.count-1 {
  grid-template-columns: minmax(0, 74%);
}
.weibo-media.count-2,
.weibo-media.count-4 {
  grid-template-columns: repeat(2, 1fr);
}
.weibo-media figure {
  position: relative;
  overflow: hidden;
  margin: 0;
  border-radius: 7px;
  background: #f2f4f7;
}
.weibo-media img {
  display: block;
  width: 100%;
  aspect-ratio: 1;
  object-fit: cover;
}
.weibo-media.count-1 img {
  aspect-ratio: 4 / 3;
}
.publish-warning,
.longtext-note,
.single-image-note {
  margin: 0 14px 9px;
  font-size: 11px;
  line-height: 1.5;
}
.publish-warning {
  color: #b42318;
}
.longtext-note,
.single-image-note {
  color: #667085;
}
.weibo-media button,
.media-empty + button {
  position: absolute;
  top: 6px;
  right: 6px;
}
.weibo-media button {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 50%;
  background: rgba(18, 24, 38, 0.72);
  color: white;
}
.media-empty {
  display: grid;
  height: 92px;
  margin: 0 14px 13px;
  place-items: center;
  border-radius: 7px;
  background: #f5f6f8;
  color: #98a2b3;
  font-size: 11px;
}
footer {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-top: 1px solid #f0f1f3;
}
footer span {
  padding: 10px 0;
  color: #667085;
  font-size: 11px;
  text-align: center;
}
footer span + span {
  border-left: 1px solid #f0f1f3;
}
</style>
