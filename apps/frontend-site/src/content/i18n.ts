import { ref } from 'vue'
import messages from './messages.json'

export const languages = ['ru', 'cz', 'en'] as const
export type Locale = typeof languages[number]

function preference(key: string, fallback: string): string {
  try { return localStorage.getItem(key) || fallback } catch { return fallback }
}
function savePreference(key: string, value: string) {
  try { localStorage.setItem(key, value) } catch { /* Настройки необязательны. */ }
}
const savedLocale = preference('mfs-clone-locale', 'ru')
export const locale = ref<Locale>(languages.includes(savedLocale as Locale) ? savedLocale as Locale : 'ru')
export const theme = ref(preference('mfs-clone-theme', 'light') === 'dark' ? 'dark' : 'light')

export function setLocale(value: Locale) {
  locale.value = value
  document.documentElement.lang = value === 'cz' ? 'cs' : value
  savePreference('mfs-clone-locale', value)
}
export function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme.value
  savePreference('mfs-clone-theme', theme.value)
}
export function initPreferences() {
  document.documentElement.lang = locale.value === 'cz' ? 'cs' : locale.value
  document.documentElement.dataset.theme = theme.value
}
export function t(key: string): string {
  const get = (language: Locale) => key.split('.').reduce<unknown>((value, part) =>
    value && typeof value === 'object' ? (value as Record<string, unknown>)[part] : undefined, messages[language])
  const value = get(locale.value) ?? get('ru')
  return typeof value === 'string' ? value : key
}

const copy = {
  lightTheme: ['Включить светлую тему', 'Zapnout světlý motiv', 'Use light theme'],
  darkTheme: ['Включить тёмную тему', 'Zapnout tmavý motiv', 'Use dark theme'],
  required: ['Заполните обязательные поля.', 'Vyplňte povinná pole.', 'Complete the required fields.'],
  invalidName: ['Введите имя и фамилию латиницей.', 'Zadejte jméno a příjmení latinkou.', 'Enter your full name in Latin characters.'],
  invalidPhone: ['Введите чешский номер: +420 и 9 цифр.', 'Zadejte české číslo: +420 a 9 číslic.', 'Enter a Czech number: +420 and 9 digits.'],
  invalidEmail: ['Введите полный адрес электронной почты.', 'Zadejte celou e-mailovou adresu.', 'Enter your complete email address.'],
  invalidBirthDate: ['Проверьте дату рождения: возраст от 15 до 75 лет.', 'Zkontrolujte datum narození: věk 15–75 let.', 'Check your birth date: age 15–75.'],
  invalidContact: ['Проверьте контакт для связи.', 'Zkontrolujte kontaktní údaj.', 'Check your contact details.'],
  tooLong: ['Превышена допустимая длина поля.', 'Pole je příliš dlouhé.', 'This value is too long.'],
  fileRequired: ['Добавьте документ.', 'Přidejte dokument.', 'Add a document.'],
  fileType: ['Допустимы JPG, PNG, WebP и PDF.', 'Povoleny jsou JPG, PNG, WebP a PDF.', 'Use JPG, PNG, WebP or PDF.'],
  fileEmpty: ['Файл пуст. Выберите другой.', 'Soubor je prázdný. Vyberte jiný.', 'This file is empty. Choose another.'],
  fileLarge: ['Файл должен быть не больше 25 МБ.', 'Soubor může mít nejvýše 25 MB.', 'Each file must be at most 25 MB.'],
  filesLarge: ['Общий размер документов — не более 90 МБ, максимум 20 файлов.', 'Celkem nejvýše 90 MB a 20 souborů.', 'Upload up to 20 files, at most 90 MB in total.'],
  fileHint: ['JPG, PNG, WebP или PDF · до 25 МБ на файл', 'JPG, PNG, WebP nebo PDF · do 25 MB na soubor', 'JPG, PNG, WebP or PDF · up to 25 MB per file'],
  remove: ['Удалить файл', 'Odebrat soubor', 'Remove file'],
  send: ['Отправить заявку', 'Odeslat žádost', 'Submit application'],
  sending: ['Отправляем…', 'Odesílání…', 'Sending…'],
  consent: ['Подтвердите согласие на обработку данных.', 'Potvrďte souhlas se zpracováním údajů.', 'Confirm your consent to data processing.'],
  connection: ['Не удалось связаться с сервером. Данные остались в форме — попробуйте снова.', 'Nelze se spojit se serverem. Údaje zůstaly ve formuláři — zkuste to znovu.', 'Cannot reach the server. Your data remains in the form — please retry.'],
  timeout: ['Сервер не ответил вовремя. Можно повторить отправку: повторная анкета не создаётся.', 'Server neodpověděl včas. Můžete odeslat znovu — duplicitní žádost nevznikne.', 'The server timed out. You can retry — this will not create a duplicate application.'],
  server: ['Сервис временно недоступен. Попробуйте позже или напишите нам в Telegram.', 'Služba je dočasně nedostupná. Zkuste to později nebo nám napište na Telegram.', 'The service is temporarily unavailable. Try later or contact us on Telegram.'],
  invalidPayload: ['Сервер отклонил данные. Проверьте поля и документы.', 'Server odmítl údaje. Zkontrolujte pole a dokumenty.', 'The server rejected the data. Check your fields and documents.'],
  conflict: ['Телефон и email относятся к разным анкетам. Свяжитесь с поддержкой.', 'Telefon a e-mail patří různým žádostem. Kontaktujte podporu.', 'The phone and email match different applications. Contact support.'],
  rateLimit: ['Слишком много попыток. Подождите немного и повторите.', 'Příliš mnoho pokusů. Chvíli počkejte a opakujte.', 'Too many attempts. Please wait and retry.'],
  incomplete: ['Сервер не подтвердил сохранение заявки. Попробуйте ещё раз или свяжитесь с поддержкой.', 'Server nepotvrdil uložení žádosti. Zkuste to znovu nebo kontaktujte podporu.', 'The server did not confirm your application. Retry or contact support.'],
  successTitle: ['Заявка отправлена!', 'Žádost byla odeslána!', 'Application submitted!'],
  successLead: ['Спасибо, что выбрали MFS Fleet.', 'Děkujeme, že jste si vybrali MFS Fleet.', 'Thank you for choosing MFS Fleet.'],
  successDescription: ['Ваша анкета и документы получены. Менеджер свяжется с вами по указанному контакту.', 'Obdrželi jsme váš formulář a dokumenty. Manažer vás bude kontaktovat.', 'We received your application and documents. Our manager will contact you.'],
  existingTitle: ['Ваша заявка уже получена', 'Vaši žádost již máme', 'We already have your application'],
  existingDescription: ['По этому телефону или email уже есть анкета. Повторная отправка не изменила прежние данные и документы. Если нужно их обновить, напишите в поддержку.', 'Pro tento telefon nebo e-mail již existuje žádost. Opakované odeslání nezměnilo původní údaje ani dokumenty. Pro změny kontaktujte podporu.', 'An application already exists for this phone or email. Resubmitting did not update its data or documents. Contact support to make changes.'],
  home: ['Вернуться на главную', 'Zpět na hlavní stránku', 'Back to home'],
  contactLabel: ['Контакт для связи', 'Kontaktní údaj', 'Contact details'],
  czech: ['Чехия', 'Česká republika', 'Czech Republic'],
  ukraine: ['Украина', 'Ukrajina', 'Ukraine'],
  turkey: ['Турция', 'Turecko', 'Turkey'],
  india: ['Индия', 'Indie', 'India'],
  slovakia: ['Словакия', 'Slovensko', 'Slovakia'],
  idFront: ['ID-карта — лицевая сторона', 'Občanský průkaz — přední strana', 'ID card — front'],
  idBack: ['ID-карта — обратная сторона', 'Občanský průkaz — zadní strana', 'ID card — back'],
  passport: ['Паспорт — лицевая сторона', 'Cestovní pas — přední strana', 'Passport — photo page'],
  residence: ['Виза / ВНЖ — лицевая сторона', 'Vízum / povolení k pobytu — přední strana', 'Visa / residence permit — front'],
  privacy: ['Как используются данные', 'Jak zpracováváme údaje', 'How your data is used'],
  privacyText: ['Анкета и документы передаются May Fleet Solutions для оформления заявки в Bolt Food. Доступ к документам предоставляется сотрудникам с правами администратора. Вопросы об обработке и удалении данных: may.fleet.solutions@gmail.com.', 'Formulář a dokumenty jsou předány May Fleet Solutions pro zpracování žádosti o Bolt Food. Dokumenty jsou přístupné pracovníkům s administrátorským oprávněním. Dotazy ke zpracování a výmazu: may.fleet.solutions@gmail.com.', 'Your application and documents are sent to May Fleet Solutions for Bolt Food onboarding. Documents are available to staff with administrator access. Questions about processing or deletion: may.fleet.solutions@gmail.com.'],
} as const
export type CopyKey = keyof typeof copy
export function ui(key: CopyKey): string { return copy[key][languages.indexOf(locale.value)] }
