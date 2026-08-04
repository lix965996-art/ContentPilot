import type { WechatFormatProfile } from '@/types/business'

export const defaultWechatProfile: WechatFormatProfile = {
  theme: 'clean',
  accent_color: '#1677ff',
  font_size: 16,
  line_height: 1.8,
  paragraph_spacing: 16,
  first_line_indent: false,
  link_footnotes: true,
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;')
}

export function buildPreviewHtml(content: string) {
  const text = content.trim() || '暂无内容，生成平台版本后可在此预览。'
  return escapeHtml(text)
    .replace(/^###\s+(.+)$/gm, '<h5>$1</h5>')
    .replace(/^##\s+(.+)$/gm, '<h4>$1</h4>')
    .replace(/^#\s+(.+)$/gm, '<h3>$1</h3>')
    .replace(/^(?:[一二三四五六七八九十]+、|\d+[、.])\s*(.+)$/gm, '<h4>$&</h4>')
    .replace(/^•\s+(.+)$/gm, '<div class="preview-list-item">• $1</div>')
    .replace(/\n{2,}/g, '</p><p>')
    .replace(/\n/g, '<br>')
}

export function buildWeiboPreviewTitle(title: string, content: string) {
  const cleanTitle = title.trim()
  return cleanTitle && !content.trim().startsWith(cleanTitle) ? cleanTitle : ''
}

export function buildWeiboPreviewText(title: string, content: string, hashtags: string[]) {
  const cleanTitle = title.trim()
  const cleanContent = content.trim()
  const hook = cleanTitle && !cleanContent.startsWith(cleanTitle) ? cleanTitle : ''
  const body = [hook, cleanContent].filter(Boolean).join('\n\n')
  const topics = hashtags
    .map((tag) => tag.replace(/#/g, '').trim())
    .filter(Boolean)
    .map((topic) => `#${topic}#`)
    .join(' ')
  return [body, topics].filter(Boolean).join('\n\n')
}
