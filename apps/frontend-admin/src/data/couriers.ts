import type {
  Courier,
  CourierDocument,
  DocumentReviewStatus,
} from '../types/courier'

type CourierSeed = Omit<Courier, 'documentFiles'>

const courierSeeds: CourierSeed[] = [
  { id: '7b21c140', fullName: 'Анна Коваль', email: 'anna.koval@example.com', phone: '+43 660 284 1190', birthDate: '1996-04-18', city: 'Вена', address: 'Favoritenstraße 82, 1100 Wien', citizenship: 'Украина', bank: 'AT12 •••• 1842', contactPlatform: 'Telegram', contact: '@anna_koval', source: 'Рекомендация', consent: true, platforms: [{ name: 'Wolt', status: 'active' }], documents: 3, documentStatus: 'Проверены', updated: '26.08.2026' },
  { id: 'e41a5bd9', fullName: 'Марко Йованович', email: 'marko.j@example.com', phone: '+43 676 421 7055', birthDate: '1992-11-03', city: 'Грац', address: 'Annenstraße 31, 8020 Graz', citizenship: 'Сербия', bank: 'AT64 •••• 9021', contactPlatform: 'WhatsApp', contact: '+43 676 421 7055', source: 'Сайт MFS', consent: true, platforms: [{ name: 'Lieferando', status: 'active' }], documents: 4, documentStatus: 'Проверены', updated: '25.08.2026' },
  { id: '20f88e71', fullName: 'Олексій Бондар', email: 'o.bondar@example.com', phone: '+43 664 903 2168', birthDate: '1998-07-22', city: 'Вена', address: 'Brigittenauer Lände 14, 1200 Wien', citizenship: 'Украина', bank: 'AT28 •••• 0039', contactPlatform: 'Telegram', contact: '@obondar', source: 'Партнёр', consent: true, platforms: [{ name: 'Wolt', status: 'review' }, { name: 'Bolt Food', status: 'active' }], documents: 2, documentStatus: '1 на проверке', updated: '24.08.2026' },
  { id: '9d33b81a', fullName: 'Елена Димитрова', email: 'elena.d@example.com', phone: '+43 699 118 2740', birthDate: '1994-01-14', city: 'Линц', address: 'Landstraße 46, 4020 Linz', citizenship: 'Болгария', bank: 'AT91 •••• 6204', contactPlatform: 'Signal', contact: '+43 699 118 2740', source: 'Реклама', consent: true, platforms: [{ name: 'Lieferando', status: 'active' }], documents: 3, documentStatus: 'Проверены', updated: '22.08.2026' },
  { id: '611ab3d4', fullName: 'Давид Нвару', email: 'david.n@example.com', phone: '+43 650 774 1982', birthDate: '1990-09-08', city: 'Зальцбург', address: 'Linzer Gasse 27, 5020 Salzburg', citizenship: 'Нигерия', bank: 'AT44 •••• 7718', contactPlatform: 'WhatsApp', contact: '+43 650 774 1982', source: 'Рекомендация', consent: false, platforms: [{ name: 'Wolt', status: 'blocked' }], documents: 2, documentStatus: 'Нужна замена', updated: '20.08.2026' },
  { id: 'bf0e6257', fullName: 'Катерина Мельник', email: 'kateryna.m@example.com', phone: '+43 681 229 4007', birthDate: '1997-06-11', city: 'Вена', address: 'Praterstraße 52, 1020 Wien', citizenship: 'Украина', bank: 'AT03 •••• 1156', contactPlatform: 'Telegram', contact: '@k_melnyk', source: 'Сайт MFS', consent: true, platforms: [{ name: 'Bolt Food', status: 'review' }], documents: 1, documentStatus: 'На проверке', updated: '18.08.2026' },
  { id: 'aa8c95f0', fullName: 'Пётр Новак', email: 'piotr.nowak@example.com', phone: '+43 670 841 3002', birthDate: '1989-12-27', city: 'Грац', address: 'Jakominiplatz 4, 8010 Graz', citizenship: 'Польша', bank: 'AT73 •••• 4481', contactPlatform: 'WhatsApp', contact: '+43 670 841 3002', source: 'Партнёр', consent: true, platforms: [{ name: 'Wolt', status: 'active' }, { name: 'Lieferando', status: 'active' }], documents: 5, documentStatus: 'Проверены', updated: '14.08.2026' },
  { id: '32f410dc', fullName: 'Милош Павлович', email: 'milos.p@example.com', phone: '+43 664 711 5088', birthDate: '1995-03-02', city: 'Линц', address: 'Wiener Straße 89, 4020 Linz', citizenship: 'Сербия', bank: 'AT56 •••• 8300', contactPlatform: 'Signal', contact: '+43 664 711 5088', source: 'Рекомендация', consent: true, platforms: [], documents: 0, documentStatus: 'Нет документов', updated: '11.08.2026' },
  { id: 'c9d46f12', fullName: 'София Марин', email: 'sofia.marin@example.com', phone: '+43 677 291 6401', birthDate: '1993-08-19', city: 'Вена', address: 'Hütteldorfer Straße 115, 1140 Wien', citizenship: 'Румыния', bank: 'AT18 •••• 2917', contactPlatform: 'Telegram', contact: '@sofia_marin', source: 'Сайт MFS', consent: true, platforms: [{ name: 'Lieferando', status: 'active' }], documents: 4, documentStatus: 'Проверены', updated: '09.08.2026' },
]

const documentTemplates = [
  { originalName: 'passport_scan.pdf', typeLabel: 'Паспорт', purposeLabel: 'Проверка личности', contentType: 'application/pdf', size: 1_485_210 },
  { originalName: 'residence_permit.pdf', typeLabel: 'Вид на жительство', purposeLabel: 'Право на работу', contentType: 'application/pdf', size: 924_880 },
  { originalName: 'driving_licence.jpg', typeLabel: 'Водительское удостоверение', purposeLabel: 'Профиль курьера', contentType: 'image/jpeg', size: 2_380_410 },
  { originalName: 'bank_confirmation.pdf', typeLabel: 'Подтверждение счёта', purposeLabel: 'Выплаты', contentType: 'application/pdf', size: 638_920 },
  { originalName: 'data_consent.pdf', typeLabel: 'Согласие на обработку', purposeLabel: 'Юридический архив', contentType: 'application/pdf', size: 281_430 },
]

function reviewStatusFor(courier: CourierSeed, index: number): DocumentReviewStatus {
  const summary = courier.documentStatus.toLocaleLowerCase('ru')
  if (summary.includes('замен')) return index === 0 ? 'rejected' : 'ready'
  if (summary.includes('проверк')) return index === 0 ? 'processing' : 'ready'
  return 'ready'
}

function buildDocuments(courier: CourierSeed): CourierDocument[] {
  return Array.from({ length: courier.documents }, (_, index) => {
    const template = documentTemplates[index % documentTemplates.length]
    const suffix = String(index + 1).padStart(2, '0')
    const createdAt = `2026-08-${String(8 + index).padStart(2, '0')}T09:30:00Z`

    return {
      id: `${courier.id}-doc-${suffix}`,
      typeLabel: template.typeLabel,
      purposeLabel: template.purposeLabel,
      reviewStatus: reviewStatusFor(courier, index),
      file: {
        id: `${courier.id}-file-${suffix}`,
        originalName: template.originalName,
        contentType: template.contentType,
        size: template.size + index * 17_320,
        status: 'AVAILABLE',
        ownerId: courier.id,
        createdAt,
      },
      createdAt,
      updatedAt: `2026-08-${String(18 + index).padStart(2, '0')}T14:15:00Z`,
    }
  })
}

export function createDemoCouriers(): Courier[] {
  return courierSeeds.map((courier) => ({
    ...courier,
    platforms: courier.platforms.map((platform) => ({ ...platform })),
    documentFiles: buildDocuments(courier),
  }))
}
