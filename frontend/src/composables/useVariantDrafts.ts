import { ref, watch, type Ref } from 'vue'
import type { Variant } from '@/types/business'

export interface VariantDraftPayload {
  title: string
  content_text: string
  hashtags: string[]
}

interface LocalVariantDraft extends VariantDraftPayload {
  variantId: number
  savedAt: number
}

interface DraftEntry {
  payload: VariantDraftPayload
  revision: number
  acknowledged: number
  error: string
  saving?: Promise<boolean>
  timer?: ReturnType<typeof setTimeout>
  recovery?: LocalVariantDraft
}

const draftKey = (id: number) => `contentpilot_studio_draft:${id}`
const clone = (value: VariantDraftPayload): VariantDraftPayload => ({
  ...value,
  hashtags: [...value.hashtags],
})
const same = (left: VariantDraftPayload, right: VariantDraftPayload) =>
  left.title === right.title &&
  left.content_text === right.content_text &&
  JSON.stringify(left.hashtags) === JSON.stringify(right.hashtags)

export function useVariantDrafts(options: {
  current: Ref<Variant | undefined>
  editing: VariantDraftPayload
  fromVariant: (variant: Variant) => VariantDraftPayload
  update: (id: number, payload: VariantDraftPayload) => Promise<Variant>
  onSaved: (variant: Variant) => void
  errorMessage: (error: unknown) => string
  debounceMs?: number
}) {
  const saved = ref(true)
  const autosaveState = ref<'SAVED' | 'DIRTY' | 'SAVING' | 'ERROR'>('SAVED')
  const autosaveError = ref('')
  const lastSavedAt = ref<number>()
  const recoveryDraft = ref<LocalVariantDraft>()
  const entries = new Map<number, DraftEntry>()
  let editorId: number | undefined
  let syncing = false
  let disposed = false

  function write(id: number, payload: VariantDraftPayload) {
    try {
      localStorage.setItem(
        draftKey(id),
        JSON.stringify({ ...clone(payload), variantId: id, savedAt: Date.now() }),
      )
    } catch {
      // Server saving remains available when browser storage is unavailable.
    }
  }

  function clear(id: number) {
    try {
      localStorage.removeItem(draftKey(id))
    } catch {
      // A storage failure must not prevent a server save.
    }
  }

  function read(id: number) {
    try {
      const raw = localStorage.getItem(draftKey(id))
      if (!raw) return
      const value = JSON.parse(raw) as LocalVariantDraft
      if (
        value.variantId === id &&
        typeof value.title === 'string' &&
        typeof value.content_text === 'string' &&
        Array.isArray(value.hashtags) &&
        value.hashtags.every((tag) => typeof tag === 'string') &&
        typeof value.savedAt === 'number'
      )
        return value
      clear(id)
    } catch {
      // Invalid or inaccessible local drafts do not replace server content.
    }
  }

  function showState() {
    const entry = editorId === undefined ? undefined : entries.get(editorId)
    const dirty = Boolean(entry && entry.revision !== entry.acknowledged)
    saved.value = !dirty
    autosaveError.value = entry?.error || ''
    autosaveState.value = entry?.saving
      ? 'SAVING'
      : entry?.error
        ? 'ERROR'
        : dirty
          ? 'DIRTY'
          : 'SAVED'
    recoveryDraft.value = entry?.recovery
  }

  function replaceEditing(payload: VariantDraftPayload) {
    syncing = true
    Object.assign(options.editing, clone(payload))
    syncing = false
  }

  function syncCurrent() {
    const variant = options.current.value
    editorId = variant?.id
    if (!variant) {
      replaceEditing({ title: '', content_text: '', hashtags: [] })
      showState()
      return
    }
    const server = options.fromVariant(variant)
    let entry = entries.get(variant.id)
    if (!entry) {
      const recovery = read(variant.id)
      entry = { payload: clone(server), revision: 0, acknowledged: 0, error: '', recovery }
      if (recovery && same(recovery, server)) {
        clear(variant.id)
        entry.recovery = undefined
      }
      entries.set(variant.id, entry)
    } else if (entry.revision === 0 && !entry.saving) {
      entry.payload = clone(server)
    }
    // A late response for this version cannot replace a newer local revision.
    replaceEditing(entry.payload)
    showState()
  }

  function stage() {
    if (syncing || disposed || editorId === undefined) return
    const entry = entries.get(editorId)
    if (!entry || same(entry.payload, options.editing)) return
    entry.payload = clone(options.editing)
    entry.revision += 1
    entry.error = ''
    entry.recovery = undefined
    // Persist synchronously: switching versions or closing the page has no debounce gap.
    write(editorId, entry.payload)
    if (entry.timer) clearTimeout(entry.timer)
    const id = editorId
    entry.timer = setTimeout(() => {
      entry.timer = undefined
      void save(id)
    }, options.debounceMs ?? 1500)
    showState()
  }

  async function save(id = editorId): Promise<boolean> {
    if (id === undefined) return false
    if (id === editorId) stage()
    const entry = entries.get(id)
    if (!entry) return false
    if (entry.timer) clearTimeout(entry.timer)
    entry.timer = undefined
    if (entry.saving) return entry.saving
    if (entry.revision === entry.acknowledged) return true
    entry.error = ''
    const run = async () => {
      // Serialize each version's writes so an older request cannot win on the server.
      while (!disposed && entries.get(id) === entry && entry.acknowledged < entry.revision) {
        const revision = entry.revision
        const payload = clone(entry.payload)
        try {
          const variant = await options.update(id, payload)
          entry.acknowledged = revision
          if (entry.revision === revision) clear(id)
          if (!disposed && entries.get(id) === entry) {
            options.onSaved(variant)
            if (editorId === id && entry.revision === revision) lastSavedAt.value = Date.now()
          }
        } catch (error) {
          entry.error = options.errorMessage(error)
          write(id, entry.payload)
          return false
        }
      }
      return entry.acknowledged === entry.revision
    }
    // Queue the loop after saving is installed, including synchronously rejected requests.
    entry.saving = Promise.resolve()
      .then(run)
      .finally(() => {
        entry.saving = undefined
        if (!disposed) showState()
      })
    showState()
    return entry.saving
  }

  function restore() {
    const draft = recoveryDraft.value
    if (!draft || draft.variantId !== editorId) return false
    replaceEditing(draft)
    stage()
    return true
  }

  function discard() {
    if (editorId === undefined) return
    clear(editorId)
    const entry = entries.get(editorId)
    if (entry) entry.recovery = undefined
    showState()
  }

  function forget(id: number) {
    const entry = entries.get(id)
    if (entry?.timer) clearTimeout(entry.timer)
    entries.delete(id)
    clear(id)
  }

  const stopWatching = watch(options.editing, stage, { deep: true, flush: 'sync' })
  function dispose() {
    stage()
    disposed = true
    stopWatching()
    for (const [id, entry] of entries) {
      if (entry.timer) clearTimeout(entry.timer)
      if (entry.revision !== entry.acknowledged) write(id, entry.payload)
    }
  }

  return {
    saved,
    autosaveState,
    autosaveError,
    lastSavedAt,
    recoveryDraft,
    syncCurrent,
    stage,
    save,
    restore,
    discard,
    forget,
    dispose,
    replaceEditing,
  }
}
