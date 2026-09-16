import { test, expect } from '@playwright/test'
import { fillApplication, expectNoOverflow, testDocument } from './helpers'

test('главная, язык, тема, якоря и мобильная вёрстка', async ({ page }, info) => {
  const errors: string[] = []
  page.on('pageerror', error => errors.push(error.message))
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/')
  await expect(page.locator('h1')).toContainText('Стань курьером')
  await expectNoOverflow(page)
  await page.screenshot({ path: info.outputPath('landing.png'), fullPage: true })
  await page.getByRole('button', { name: 'EN', exact: true }).click()
  await expect(page.locator('h1')).not.toContainText('Стань курьером')
  await page.getByRole('button', { name: 'CZ', exact: true }).click()
  await expect(page.locator('html')).toHaveAttribute('lang', 'cs')
  await page.getByRole('button', { name: 'RU', exact: true }).click()
  await page.getByRole('button', { name: 'Включить тёмную тему' }).click()
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark')
  await page.getByRole('link', { name: 'Посмотреть транспорт' }).click()
  await expect(page).toHaveURL(/#vehicles$/)
  await expect(page.locator('#vehicles')).toBeInViewport()
  await page.screenshot({ path: info.outputPath('dark-transport.png') })
  await page.locator('#vehicles a[href="/form"]').first().click()
  await expect(page.locator('.form-container')).toBeVisible()
  await expectNoOverflow(page)
  await page.screenshot({ path: info.outputPath('form.png'), fullPage: true })
  expect(errors).toEqual([])
})

test('пустая форма, файлы, гражданство и клавиатура', async ({ page }) => {
  await page.goto('/apply')
  await page.getByRole('button', { name: 'Отправить заявку', exact: true }).click()
  await expect(page.getByRole('radio', { name: /Bolt Food/ })).toBeFocused()
  await page.keyboard.press('Space')
  await expect(page.getByRole('radio', { name: /Bolt Food/ })).toHaveAttribute('aria-checked', 'true')
  await page.locator('#citizenship').selectOption('cz')
  await expect(page.locator('#identity')).toContainText('ID-карта')
  await page.locator('input[type=file]').first().setInputFiles(testDocument)
  await expect(page.locator('.file-item')).toHaveCount(1)
  await page.locator('#citizenship').selectOption('ua')
  await expect(page.locator('.file-item')).toHaveCount(0)
  await page.locator('input[type=file]').first().setInputFiles({ name: 'bad.html', mimeType: 'text/html', buffer: Buffer.from('not a document') })
  await expect(page.locator('#identity-error')).toContainText('Допустимы')
  await page.getByRole('button', { name: 'Удалить файл: bad.html' }).click()
  await expect(page.locator('.file-item')).toHaveCount(0)
})

test('ошибка сервера, повтор, запрет двойной отправки и успех', async ({ page }) => {
  let calls = 0
  let multipart = ''
  await page.route('**/api/courier', async route => {
    calls++
    multipart = route.request().postData() || ''
    if (calls === 1) await route.fulfill({ status: 503, json: { detail: 'Unavailable' } })
    else { await new Promise(resolve => setTimeout(resolve, 400)); await route.fulfill({ status: 201, json: { id: 'saved-id' } }) }
  })
  await fillApplication(page)
  await page.getByRole('button', { name: 'Отправить заявку', exact: true }).click()
  await expect(page.getByRole('alert')).toContainText('временно недоступен')
  await expect(page.locator('#email')).toHaveValue('frontend-site@example.test')
  await expect(page.locator('.file-item')).toHaveCount(2)
  await page.getByRole('button', { name: 'Отправить заявку', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Отправляем…' })).toBeDisabled()
  await expect(page.locator('h1')).toHaveText('Заявка отправлена!')
  expect(calls).toBe(2)
  expect(multipart).toContain('name="payload"')
  expect(multipart).toContain('"platform":"bolt_food"')
  expect(multipart).toContain('name="files"; filename="synthetic-document.png"')
  expect(await page.evaluate(() => Object.keys(localStorage).some(key => /email|phone|document|application/.test(key)))).toBe(false)
})

test('повторная анкета и защита от ложного успеха по прямой ссылке', async ({ page }) => {
  await page.goto('/success/bolt')
  await expect(page).toHaveURL(/\/form$/)
  await page.route('**/api/courier', route => route.fulfill({ status: 200, json: { id: 'existing-id' } }))
  await fillApplication(page)
  await page.getByRole('button', { name: 'Отправить заявку', exact: true }).click()
  await expect(page.locator('h1')).toHaveText('Ваша заявка уже получена')
  await expect(page.locator('.instructions')).toContainText('не изменила')
})
