import { blueskyTextLength, buildBlueskyText } from '@/utils/bluesky'

/** Both adapters send the same title, body and normalized topics. */
export const buildMastodonText = buildBlueskyText

/** Mastodon counts graphemes, reserving a fixed length for each URL. */
export function mastodonTextLength(text: string, charactersReservedPerUrl = 23): number {
  const reserved = Math.max(0, charactersReservedPerUrl)
  const urls = /https?:\/\/[^\s<>]+/giu
  let length = 0
  let cursor = 0
  for (const match of text.matchAll(urls)) {
    const start = match.index
    const url = match[0].replace(/[.,!?;:)\]}。，！？；：）】]+$/u, '')
    length += blueskyTextLength(text.slice(cursor, start)) + reserved
    cursor = start + url.length
  }
  return length + blueskyTextLength(text.slice(cursor))
}

export function mastodonLimits(config?: {
  maxCharacters?: number
  charactersReservedPerUrl?: number
  maxMediaAttachments?: number
}) {
  return {
    maxCharacters: config?.maxCharacters && config.maxCharacters > 0 ? config.maxCharacters : 500,
    charactersReservedPerUrl: config?.charactersReservedPerUrl ?? 23,
    maxMediaAttachments: Math.min(4, Math.max(0, config?.maxMediaAttachments ?? 4)),
  }
}
