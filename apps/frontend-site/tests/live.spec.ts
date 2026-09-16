import { test, expect } from '@playwright/test'
import { fillApplication } from './helpers'

test('живой backend: документы готовы, повтор возвращает ту же анкету', async ({ page }, info) => {
  const suffix = Date.now().toString().slice(-8)
  const email = `frontend-site-${Date.now()}@example.test`
  const phone = `+4207${suffix}`
  await fillApplication(page, email, phone)
  const createdResponse = page.waitForResponse(response => response.url().endsWith('/api/courier') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Отправить заявку', exact: true }).click()
  const response = await createdResponse
  expect(response.status()).toBe(201)
  const created = await response.json()
  expect(created.documents).toHaveLength(2)
  expect(created.platform_accounts[0].platform).toBe('bolt_food')
  expect(created.documents.map((document: {type: string}) => document.type)).toEqual(expect.arrayContaining(['passport', 'residence_permit']))
  for (const document of created.documents) {
    expect(document.file.status).toBe('ready')
    expect(document.file.size).toBeGreaterThan(0)
  }
  await expect(page.locator('h1')).toHaveText('Заявка отправлена!')
  await page.screenshot({ path: info.outputPath('live-success.png'), fullPage: true })
  await fillApplication(page, email, phone)
  const existingResponse = page.waitForResponse(response => response.url().endsWith('/api/courier') && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Отправить заявку', exact: true }).click()
  const repeated = await existingResponse
  expect(repeated.status()).toBe(200)
  const existing = await repeated.json()
  expect(existing.id).toBe(created.id)
  expect(existing.documents.map((document: {id: string}) => document.id).sort()).toEqual(created.documents.map((document: {id: string}) => document.id).sort())
  await expect(page.locator('h1')).toHaveText('Ваша заявка уже получена')
  await info.attach('result', { body: JSON.stringify({ courierId: created.id, created: response.status(), repeated: repeated.status(), readyDocuments: created.documents.length }), contentType: 'application/json' })
})
