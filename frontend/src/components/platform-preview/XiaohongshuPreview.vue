<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Bookmark, Heart, MessageCircle, X } from 'lucide-vue-next'
import PlatformIcon from '@/components/PlatformIcon.vue'
import type { MediaAsset } from '@/types/business'

const props = defineProps<{
  accountName: string
  title: string
  contentHtml: string
  tags: string[]
  media: MediaAsset[]
  removingId?: number
}>()

const emit = defineEmits<{
  remove: [item: MediaAsset]
  setCover: [item: MediaAsset]
}>()

const activeIndex = ref(0)
const currentImage = computed(() => props.media[activeIndex.value])
const topics = computed(() =>
  props.tags
    .map((tag) => tag.replace(/#/g, '').trim())
    .filter(Boolean)
    .map((tag) => `#${tag}`),
)

watch(
  () => props.media.length,
  (length) => {
    if (!length) activeIndex.value = 0
    else if (activeIndex.value >= length) activeIndex.value = length - 1
  },
)
</script>

<template>
  <article class="xhs-phone" data-testid="xiaohongshu-platform-preview">
    <header>
      <span class="xhs-avatar"><PlatformIcon platform="XIAOHONGSHU" size="sm" /></span>
      <b>{{ accountName }}</b>
      <button>关注</button>
    </header>

    <section v-if="currentImage" class="xhs-gallery">
      <img
        :src="currentImage.thumbnailUrl || currentImage.imageUrl"
        :alt="currentImage.altText || '小红书配图'"
      />
      <span class="image-count">{{ activeIndex + 1 }}/{{ media.length }}</span>
      <button
        type="button"
        class="remove-image"
        :disabled="removingId === currentImage.id"
        :aria-label="`移除图片：${currentImage.altText || currentImage.id}`"
        title="移除这张图片"
        @click.stop="emit('remove', currentImage)"
      >
        <X :size="13" />
      </button>
      <button
        v-if="currentImage.usageType !== 'COVER'"
        type="button"
        class="set-cover"
        @click.stop="emit('setCover', currentImage)"
      >
        设为封面
      </button>
      <nav v-if="media.length > 1" aria-label="切换预览图片">
        <button
          v-for="(item, index) in media"
          :key="item.id"
          type="button"
          :class="{ active: index === activeIndex }"
          :aria-label="`查看第 ${index + 1} 张图片`"
          @click="activeIndex = index"
        />
      </nav>
    </section>
    <div v-else class="xhs-empty">添加图片后可查看笔记封面</div>

    <section class="xhs-copy">
      <h3>{{ title || '填写标题后在这里预览' }}</h3>
      <!-- contentHtml is escaped and produced by StudioPage's restricted renderer. -->
      <!-- eslint-disable-next-line vue/no-v-html -->
      <div class="xhs-body" v-html="contentHtml" />
      <p v-if="topics.length">{{ topics.join(' ') }}</p>
      <small>刚刚 · 模拟预览</small>
    </section>

    <footer>
      <span><Heart :size="15" />点赞</span>
      <span><Bookmark :size="15" />收藏</span>
      <span><MessageCircle :size="15" />评论</span>
    </footer>
  </article>
</template>

<style scoped>
.xhs-phone {
  overflow: hidden;
  max-width: 318px;
  margin: 0 auto;
  border: 1px solid #e5e7eb;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 8px 24px rgba(16, 24, 40, 0.08);
}
header {
  display: flex;
  height: 48px;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
}
.xhs-avatar {
  display: grid;
  width: 29px;
  height: 29px;
  place-items: center;
  border-radius: 50%;
  background: #fff1f3;
}
header b {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: #222;
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
header button {
  border-radius: 999px;
  background: #ff2442;
  padding: 5px 11px;
  color: #fff;
  font-size: 10px;
}
.xhs-gallery {
  position: relative;
  overflow: hidden;
  background: #f4f5f7;
}
.xhs-gallery > img {
  display: block;
  width: 100%;
  aspect-ratio: 3 / 4;
  object-fit: cover;
}
.image-count {
  position: absolute;
  top: 9px;
  right: 10px;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.55);
  padding: 3px 7px;
  color: #fff;
  font-size: 9px;
}
.remove-image {
  position: absolute;
  top: 8px;
  left: 9px;
  display: grid;
  width: 25px;
  height: 25px;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.72);
  border-radius: 50%;
  background: rgba(18, 24, 38, 0.72);
  color: #fff;
}
.set-cover {
  position: absolute;
  right: 9px;
  bottom: 20px;
  border-radius: 999px;
  background: rgba(18, 24, 38, 0.76);
  padding: 5px 9px;
  color: #fff;
  font-size: 9px;
}
.xhs-gallery nav {
  position: absolute;
  right: 0;
  bottom: 7px;
  left: 0;
  display: flex;
  justify-content: center;
  gap: 4px;
}
.xhs-gallery nav button {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.62);
}
.xhs-gallery nav button.active {
  width: 13px;
  border-radius: 999px;
  background: #fff;
}
.xhs-empty {
  display: grid;
  height: 210px;
  place-items: center;
  background: #f4f5f7;
  color: #98a2b3;
  font-size: 10px;
}
.xhs-copy {
  padding: 13px 14px 11px;
}
.xhs-copy h3 {
  margin: 0 0 8px;
  color: #202124;
  font-size: 15px;
  line-height: 1.45;
}
.xhs-body {
  max-height: 145px;
  overflow: auto;
  color: #344054;
  font-size: 11px;
  line-height: 1.75;
}
.xhs-body :deep(p) {
  margin: 6px 0;
}
.xhs-body :deep(h3),
.xhs-body :deep(h4),
.xhs-body :deep(h5) {
  margin: 9px 0 5px;
  font-size: 11px;
}
.xhs-copy p {
  margin: 8px 0 0;
  color: #133c77;
  font-size: 10px;
  line-height: 1.55;
}
.xhs-copy small {
  display: block;
  margin-top: 9px;
  color: #a1a7b3;
  font-size: 9px;
}
footer {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-top: 1px solid #f0f1f3;
  padding: 9px 5px 10px;
}
footer span {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  color: #667085;
  font-size: 9px;
}
</style>
