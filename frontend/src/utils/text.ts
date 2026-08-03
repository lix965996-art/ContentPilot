/**
 * X (Twitter) weighted character count — mirrors the backend algorithm in
 * `app/services/platform_content.py::x_weighted_length`.
 *
 * Rules:
 * - Characters in Unicode ranges (0–4351), (8192–8205), (8208–8223),
 *   (8242–8247) count as 1 unit (Latin, common punctuation).
 * - All other characters (CJK, emoji, etc.) count as 2 units.
 * - HTTP(S) URLs are replaced by a fixed weight of 23 (t.co shortening).
 */

const URL_PATTERN = /https?:\/\/[^\s]+/gi

const SINGLE_WEIGHT_RANGES: Array<[number, number]> = [
  [0, 4351],
  [8192, 8205],
  [8208, 8223],
  [8242, 8247],
]

function plainWeight(text: string): number {
  let weight = 0
  for (const char of text) {
    const code = char.codePointAt(0) ?? 0
    const isSingle = SINGLE_WEIGHT_RANGES.some(([start, end]) => code >= start && code <= end)
    weight += isSingle ? 1 : 2
  }
  return weight
}

export function xWeightedLength(value: string): number {
  let total = 0
  let offset = 0
  for (const match of value.matchAll(URL_PATTERN)) {
    const index = match.index ?? 0
    total += plainWeight(value.slice(offset, index))
    total += 23 // t.co fixed length
    offset = index + match[0].length
  }
  return total + plainWeight(value.slice(offset))
}
