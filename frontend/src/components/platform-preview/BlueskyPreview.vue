<script setup lang="ts">
import { computed } from 'vue'
import { Heart, MessageCircle, Repeat2, X } from 'lucide-vue-next'
import PlatformIcon from '@/components/PlatformIcon.vue'
import type { MediaAsset } from '@/types/business'
import { blueskyTextLength, buildBlueskyText } from '@/utils/bluesky'

const props = defineProps<{
  accountName: string
  title: string
  content: string
  tags: string[]
  media: MediaAsset[]
  removingId?: number
}>()
const emit = defineEmits<{ remove: [item: MediaAsset] }>()
const text = computed(() => buildBlueskyText(props.title, props.content, props.tags))
const length = computed(() => blueskyTextLength(text.value))
</script>

<template>
  <article class="bluesky-post" data-testid="bluesky-platform-preview">
    <header>
      <PlatformIcon platform="BLUESKY" />
      <div>
        <strong>{{ accountName }}</strong
        ><small>刚刚 · Bluesky</small>
      </div>
    </header>
    <p class="post-text">{{ text }}</p>
    <small :class="{ warning: length > 300 }">{{ length }} / 300 字符（含标题与话题）</small>
    <p v-if="media.length > 4" class="warning">最多支持 4 张图片，请移除多余图片后发布。</p>
    <section v-if="media.length" class="post-images">
      <figure v-for="item in media.slice(0, 4)" :key="item.id">
        <img :src="item.thumbnailUrl || item.imageUrl" :alt="item.altText || 'Bluesky 帖子配图'" />
        <button
          type="button"
          :disabled="removingId === item.id"
          aria-label="移除图片"
          @click="emit('remove', item)"
        >
          <X :size="13" />
        </button>
      </figure>
    </section>
    <footer>
      <span><MessageCircle :size="15" />回复</span><span><Repeat2 :size="15" />转帖</span
      ><span><Heart :size="15" />喜欢</span>
    </footer>
  </article>
</template>

<style scoped>
.bluesky-post {
  padding: 16px;
  border: 1px solid #dbe3ec;
  border-radius: 14px;
  background: #fff;
  color: #16212e;
}
header {
  display: flex;
  gap: 10px;
  align-items: center;
}
header strong,
header small {
  display: block;
}
header small,
small,
footer {
  color: #607080;
  font-size: 11px;
}
.post-text {
  margin: 14px 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: 14px;
  line-height: 1.65;
}
.warning {
  color: #b45309;
  font-size: 11px;
}
.post-images {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px;
  margin-top: 12px;
}
figure {
  position: relative;
  margin: 0;
  overflow: hidden;
  border-radius: 8px;
}
figure img {
  width: 100%;
  height: 155px;
  object-fit: cover;
}
figure button {
  position: absolute;
  top: 6px;
  right: 6px;
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border-radius: 50%;
  background: #16212ec0;
  color: #fff;
}
footer {
  display: flex;
  justify-content: space-around;
  margin-top: 15px;
}
footer span {
  display: flex;
  align-items: center;
  gap: 5px;
}
</style>
