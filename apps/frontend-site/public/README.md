# Ассеты

Бинарные файлы выгружаются вручную из проекта Claude Design
`MFS мобильный лендинг` (`08d3e60a-1acf-42f8-93ac-f2e048a53847`),
потому что API отдаёт бинарники обрезанными на 256 KiB.

| В дизайн-проекте | Здесь |
|---|---|
| `uploads/Logo.svg` | `logo.svg` (уже в репозитории) |
| `uploads/page3.png` | `scenes/intro-1.png` |
| `uploads/page1.png` | `scenes/intro-2.png` |
| `uploads/page2.png` | `scenes/intro-3.png` |
| `uploads/Gemini_Generated_Image_3m9n763m9n763m9n.png` | `transport/poster.png` |
| `uploads/Animate_this_pixel_art_illustr.mp4` | `transport/loop.mp4` |
| `uploads/Gemini_Generated_Image_dcwicgdcwicgdcwi-removebg-preview.png` | `cta/bike.png` |
| `uploads/Gemini_Generated_Image_68yiox68yiox68yi-removebg-preview.png` | `cta/phone.png` |
| `uploads/Gemini_Generated_Image_cmzyrycmzyrycmzy-removebg-preview.png` | `cta/bag.png` |

Медиа единой сцены транспорта лежит в `transport/` и использует имена
`poster.png` и `loop.mp4`.

Вёрстка не должна ломаться при отсутствующем файле: у слоёв задан фоновый цвет,
у видео — `poster`, у изображений — размеры.
