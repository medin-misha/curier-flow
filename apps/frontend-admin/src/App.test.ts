import { mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it } from 'vitest'
import App from './App.vue'

let wrapper: VueWrapper | undefined

function mountApp() {
  wrapper = mount(App, {
    global: {
      stubs: {
        Teleport: true,
      },
    },
  })
  return wrapper
}

function buttonWithText(wrapper: VueWrapper, text: string) {
  const button = wrapper.findAll('button').find((item) => item.text().trim() === text)
  if (!button) throw new Error(`Кнопка «${text}» не найдена`)
  return button
}

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  document.body.innerHTML = ''
})

describe('реестр курьеров', () => {
  it('показывает первую страницу и переключает пагинацию', async () => {
    const page = mountApp()

    expect(page.findAll('tbody tr')).toHaveLength(5)
    expect(page.get('.pagination-summary').text()).toBe('1–5 из 9')

    await page.get('[aria-label="Следующая страница"]').trigger('click')

    expect(page.findAll('tbody tr')).toHaveLength(4)
    expect(page.get('.pagination-summary').text()).toBe('6–9 из 9')
  })

  it('фильтрует записи по поиску и городу', async () => {
    const page = mountApp()

    await page.get('input[type="search"]').setValue('Анна')
    expect(page.findAll('tbody tr')).toHaveLength(1)
    expect(page.text()).toContain('Анна Коваль')
    expect(page.text()).toContain('Найдено: 1')

    await page.get('[data-od-id="city-filter"]').setValue('Грац')
    expect(page.find('.empty-state').exists()).toBe(true)
  })

  it('открывает профиль курьера с документами', async () => {
    const page = mountApp()

    await page.get('.table-action').trigger('click')

    expect(page.get('[role="dialog"]').text()).toContain('Анна Коваль')
    expect(page.get('[role="dialog"]').text()).toContain('passport_scan.pdf')
    expect(page.findAll('.document-card')).toHaveLength(3)
  })

  it('создаёт курьера после проверки обязательных полей', async () => {
    const page = mountApp()

    await buttonWithText(page, 'Создать').trigger('click')
    await page.get('form').trigger('submit')
    expect(page.get('#fullName').attributes('aria-invalid')).toBe('true')

    await page.get('#fullName').setValue('Ирина Тестова')
    await page.get('#birthDate').setValue('1991-05-12')
    await page.get('#email').setValue('irina@example.com')
    await page.get('#phone').setValue('+43 660 111 2233')
    await page.get('form').trigger('submit')

    expect(page.find('[role="dialog"]').exists()).toBe(false)
    expect(page.text()).toContain('Ирина Тестова')
    expect(page.get('.pagination-summary').text()).toBe('1–5 из 10')
    expect(page.get('[role="status"]').text()).toContain('Курьер создан')
  })
})
