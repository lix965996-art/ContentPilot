/// <reference lib="es2022.intl" />

/** Local preview of the text sent by the Bluesky publisher. */
export function buildBlueskyText(title: string, content: string, hashtags: string[]): string {
  const heading = title.trim()
  const body = content.trim()
  const text =
    heading && !body.startsWith(heading) ? [heading, body].filter(Boolean).join('\n\n') : body
  const topics = [
    ...new Set(hashtags.map((tag) => tag.replace(/#/g, '').replace(/\s/g, '').trim())),
  ]
    .filter(Boolean)
    .slice(0, 4)
    .map((tag) => `#${tag}`)
  return [text, topics.join(' ')].filter(Boolean).join('\n\n')
}

/** Bluesky counts grapheme clusters, so emoji sequences count as one character. */
export function blueskyTextLength(text: string): number {
  return [...new Intl.Segmenter(undefined, { granularity: 'grapheme' }).segment(text)].length
}
