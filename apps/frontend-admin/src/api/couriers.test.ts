import { afterEach, describe, expect, it, vi } from 'vitest'
import { configureAccessRecovery, setAccessToken } from './client'
import { bulkDeleteCouriers, bulkUpdateCourierStatus } from './couriers'

afterEach(() => {
  setAccessToken(null)
  configureAccessRecovery(null)
  vi.unstubAllGlobals()
})

describe('Авторизация массовых Courier API запросов', () => {
  it.each(['delete', 'status'] as const)('сохраняет тело и Idempotency-Key после 401 для %s', async (action) => {
    const result = action === 'delete' ? { deleted_count: 2 } : { updated_count: 0, unchanged_count: 2 }
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 401 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(result)))
    vi.stubGlobal('fetch', fetchMock)
    setAccessToken('expired-token')
    const recover = vi.fn(async () => { setAccessToken('fresh-token'); return true })
    configureAccessRecovery(recover)
    const ids = ['00000000-0000-4000-8000-000000000001', '00000000-0000-4000-8000-000000000002']
    const key = '10000000-0000-4000-8000-000000000001'
    const response = action === 'delete'
      ? await bulkDeleteCouriers(ids, key)
      : await bulkUpdateCourierStatus(ids, { platform: 'foodora', status: 'pending' }, key)
    expect(response).toEqual(action === 'delete' ? { deletedCount: 2 } : { updatedCount: 0, unchangedCount: 2 })
    expect(recover).toHaveBeenCalledTimes(1)
    expect(fetchMock).toHaveBeenCalledTimes(2)
    const [first, second] = fetchMock.mock.calls
    expect(second[0]).toBe(first[0])
    expect(second[1].body).toBe(first[1].body)
    for (const [, init] of fetchMock.mock.calls) {
      expect(new Headers(init.headers).get('Idempotency-Key')).toBe(key)
      expect(init.credentials).toBe('include')
    }
    expect(new Headers(first[1].headers).get('Authorization')).toBe('Bearer expired-token')
    expect(new Headers(second[1].headers).get('Authorization')).toBe('Bearer fresh-token')
  })
})
