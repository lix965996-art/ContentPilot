<script setup lang="ts">
import { nextTick, reactive, ref, watch } from 'vue'
import DOMPurify from 'dompurify'
import { Check, Clipboard, LayoutTemplate, RefreshCw } from 'lucide-vue-next'
import { ElMessage } from 'element-plus'
import { getApiErrorMessage } from '@/api/client'
import { workflowApi } from '@/api/workflow'
import type { Variant, WechatFormatProfile, WechatThemeProfile } from '@/types/business'

const props = defineProps<{
  modelValue: boolean
  variant?: Variant
  contentText: string
}>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  applied: [variant: Variant]
}>()

const defaultProfile: WechatFormatProfile = {
  theme: 'clean',
  accent_color: '#1677ff',
  font_size: 16,
  line_height: 1.8,
  paragraph_spacing: 16,
  first_line_indent: false,
  link_footnotes: true,
}
const profile = reactive<WechatFormatProfile>({ ...defaultProfile })
const themes = ref<WechatThemeProfile[]>([])
const previewHtml = ref('')
const previewing = ref(false)
const applying = ref(false)
let previewSequence = 0
let previewTimer: number | undefined

function resetProfile() {
  Object.assign(profile, defaultProfile, props.variant?.formatProfileJson || {})
}

async function refreshPreview() {
  if (!props.contentText.trim()) return
  const sequence = ++previewSequence
  previewing.value = true
  try {
    const result = await workflowApi.previewWechatFormat(props.contentText, { ...profile })
    if (sequence !== previewSequence) return
    previewHtml.value = DOMPurify.sanitize(result.contentHtml, {
      ADD_ATTR: ['data-contentpilot-format'],
    })
  } catch (error) {
    if (sequence === previewSequence) ElMessage.error(getApiErrorMessage(error, '排版预览生成失败'))
  } finally {
    if (sequence === previewSequence) previewing.value = false
  }
}

function schedulePreview() {
  window.clearTimeout(previewTimer)
  previewTimer = window.setTimeout(() => void refreshPreview(), 180)
}

async function load() {
  resetProfile()
  if (!themes.value.length) themes.value = await workflowApi.wechatFormatProfiles()
  await nextTick()
  await refreshPreview()
}

function selectTheme(theme: WechatThemeProfile) {
  profile.theme = theme.key
  profile.accent_color = theme.accent_color
}

async function copyRichText() {
  if (!previewHtml.value) return
  const plainText = props.contentText
  try {
    if (typeof ClipboardItem !== 'undefined' && navigator.clipboard.write) {
      await navigator.clipboard.write([
        new ClipboardItem({
          'text/html': new Blob([previewHtml.value], { type: 'text/html' }),
          'text/plain': new Blob([plainText], { type: 'text/plain' }),
        }),
      ])
    } else {
      await navigator.clipboard.writeText(plainText)
    }
    ElMessage.success('已复制公众号富文本，可直接粘贴到编辑器')
  } catch {
    await navigator.clipboard.writeText(plainText)
    ElMessage.warning('浏览器未允许复制富文本，已改为复制纯文本')
  }
}

async function applyFormatting() {
  if (!props.variant) return
  applying.value = true
  try {
    const value = await workflowApi.formatWechatVariant(props.variant.id, { ...profile })
    emit('applied', value)
    ElMessage.success('公众号排版已保存，发布草稿时会使用此样式')
  } catch (error) {
    ElMessage.error(getApiErrorMessage(error, '保存排版失败'))
  } finally {
    applying.value = false
  }
}

watch(
  () => props.modelValue,
  (open) => {
    if (open) void load()
    else window.clearTimeout(previewTimer)
  },
)
watch(profile, schedulePreview, { deep: true })
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="微信公众号排版助手"
    width="min(1120px, 94vw)"
    class="wechat-formatter-dialog"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div class="wechat-formatter-shell" data-testid="wechat-formatter">
      <aside class="wechat-format-controls">
        <div class="format-intro">
          <LayoutTemplate :size="20" />
          <div>
            <strong>选择一套公众号版式</strong>
            <p>只调整排版，不改动文章内容。保存后预览、复制和公众号草稿发布保持一致。</p>
          </div>
        </div>

        <label class="format-label">版式主题</label>
        <button
          v-for="theme in themes"
          :key="theme.key"
          class="theme-option"
          :class="{ active: profile.theme === theme.key }"
          type="button"
          @click="selectTheme(theme)"
        >
          <i :style="{ backgroundColor: theme.accent_color }" />
          <span
            ><b>{{ theme.name }}</b
            ><small>{{ theme.description }}</small></span
          >
          <Check v-if="profile.theme === theme.key" :size="16" />
        </button>

        <div class="format-field color-field">
          <label>主题色</label>
          <el-color-picker v-model="profile.accent_color" />
          <el-input v-model="profile.accent_color" maxlength="7" />
        </div>
        <div class="format-field">
          <label>正文字号 · {{ profile.font_size }}px</label>
          <el-slider v-model="profile.font_size" :min="14" :max="20" :step="1" />
        </div>
        <div class="format-field">
          <label>行距 · {{ profile.line_height.toFixed(1) }}</label>
          <el-slider v-model="profile.line_height" :min="1.4" :max="2.2" :step="0.1" />
        </div>
        <div class="format-field">
          <label>段落间距 · {{ profile.paragraph_spacing }}px</label>
          <el-slider v-model="profile.paragraph_spacing" :min="8" :max="32" :step="2" />
        </div>
        <div class="format-switch">
          <span>首行缩进</span><el-switch v-model="profile.first_line_indent" />
        </div>
        <div class="format-switch">
          <span>外链转为文末脚注</span><el-switch v-model="profile.link_footnotes" />
        </div>
      </aside>

      <main class="wechat-format-preview">
        <header>
          <div><strong>公众号效果预览</strong><small>基于当前文章内容实时生成</small></div>
          <RefreshCw v-if="previewing" class="preview-spinner" :size="17" />
        </header>
        <article class="wechat-article-paper">
          <h1>{{ variant?.title }}</h1>
          <div class="wechat-article-meta">ContentPilot · 公众号文章预览</div>
          <!-- The API output is sanitized again with DOMPurify before rendering. -->
          <!-- eslint-disable-next-line vue/no-v-html -->
          <div class="wechat-rich-content" v-html="previewHtml" />
        </article>
      </main>
    </div>

    <template #footer>
      <span class="formatter-footer-note">富文本复制包含内联样式，适配公众号编辑器粘贴。</span>
      <el-button @click="copyRichText"><Clipboard :size="15" />复制公众号格式</el-button>
      <el-button type="primary" :loading="applying" @click="applyFormatting"
        >保存并用于发布</el-button
      >
    </template>
  </el-dialog>
</template>
