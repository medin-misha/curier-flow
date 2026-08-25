import type { Bike } from '@/features/landing/scene.types'

export const bikes: Bike[] = [
  {
    slug: 'urban-e1',
    name: 'MFS Urban E1',
    media: {
      poster: '/bikes/urban-e1/poster.png',
      video: '/bikes/urban-e1/loop.mp4',
      focus: '58%',
    },
    specs: [
      { label: 'АКБ', value: '48V · 20Ah', note: 'зарядка 4–5 часов' },
      { label: 'ЗАПАС ХОДА', value: 'до 65 км', note: 'на одном заряде' },
    ],
    description: [
      'Электровелосипед-фэтбайк для города. Выдаём заряженным, с креплением под термо-сумку.',
    ],
    price: { amount: 'от 1750 CZK', period: 'в неделю' },
  },
]
