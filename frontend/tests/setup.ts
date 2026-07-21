import { afterEach, beforeEach } from 'vitest'
import { cleanup } from '@testing-library/vue'

beforeEach(() => {
  localStorage.clear()
})

afterEach(() => {
  cleanup()
})
