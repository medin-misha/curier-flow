import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

/**
 * CSS Modules переименовывает ссылки на анимации в scoped-имена, а @keyframes
 * из глобального файла остаются с исходными. Тогда анимация молча не
 * применяется — а правила, которые ставят opacity: 0 и рассчитывают на
 * заливку both, оставляют элемент невидимым навсегда.
 */
function moduleFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name)
    if (entry.isDirectory()) return moduleFiles(path)
    return entry.name.endsWith('.module.css') ? [path] : []
  })
}

describe('анимации в CSS-модулях', () => {
  it('каждый используемый keyframe объявлен в том же модуле', () => {
    const broken: string[] = []

    for (const file of moduleFiles('src')) {
      const css = readFileSync(file, 'utf8')
      const declared = new Set(
        Array.from(css.matchAll(/@keyframes\s+([A-Za-z0-9_-]+)/g), (m) => m[1]),
      )
      const used = Array.from(
        css.matchAll(/animation(?:-name)?:\s*([A-Za-z][A-Za-z0-9_-]*)/g),
        (m) => m[1],
      ).filter((name) => name !== 'none')

      for (const name of used) {
        if (!declared.has(name)) broken.push(`${file}: ${name}`)
      }
    }

    expect(broken).toEqual([])
  })
})
