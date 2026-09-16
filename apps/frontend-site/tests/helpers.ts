import { expect, type Page } from '@playwright/test'

export const testDocument = { name: 'synthetic-document.png', mimeType: 'image/png', buffer: Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aS1EAAAAASUVORK5CYII=', 'base64') }
export async function fillApplication(page: Page, email = 'frontend-site@example.test', phone = '+420777123456') {
  await page.goto('/form')
  await page.getByRole('radio', { name: /Bolt Food/ }).click()
  await page.locator('#fullName').fill('Frontend Test')
  await page.locator('#city').fill('Praha')
  await page.locator('#phone').fill(phone)
  await page.locator('#email').fill(email)
  await page.locator('#birthDate').fill('2000-01-01')
  await page.locator('#address').fill('Synthetic test address 1')
  await page.getByRole('radio', { name: 'Telegram', exact: true }).check()
  await page.locator('#contact').fill('@frontend_test')
  await page.locator('#bankAccount').fill('123456789/0100')
  await page.locator('#citizenship').selectOption('ua')
  await page.locator('#source').fill('frontend-site-e2e')
  await page.locator('input[type=file]').nth(0).setInputFiles(testDocument)
  await page.locator('input[type=file]').nth(1).setInputFiles({ ...testDocument, name: 'synthetic-residence.png' })
  await page.locator('#consent').check()
}
export async function expectNoOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
}
