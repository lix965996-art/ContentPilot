<script setup lang="ts">
import { computed, ref, watch } from 'vue'

const props = withDefaults(defineProps<{ src?: string | null; alt?: string; size?: number }>(), {
  src: null,
  alt: '用户头像',
  size: 30,
})
const fallback = '/avatars/default-cartoon.png'
const failed = ref(false)
const imageSrc = computed(() => (!failed.value && props.src ? props.src : fallback))

watch(
  () => props.src,
  () => (failed.value = false),
)
</script>

<template>
  <img
    class="user-avatar"
    :src="imageSrc"
    :alt="alt"
    :width="size"
    :height="size"
    :style="{ width: `${size}px`, height: `${size}px` }"
    @error="failed = true"
  />
</template>
