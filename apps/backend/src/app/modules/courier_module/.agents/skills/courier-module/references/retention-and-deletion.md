# Retention и удаление

DELETE Courier и DELETE Document в своей DB-транзакции сначала переводят все
связанные Files в `deleting`, затем удаляют доменные строки. S3 здесь не
вызывается. Универсальная storage-задача удаляет object, потом File; физический
DELETE File также каскадно удаляет ещё существующий Document.

Retention eligibility: `created_at <= now - days(purpose)` и legal hold
отсутствует либо истёк. Defaults: onboarding 90, compliance 1825, other 365.
Задача выбирает ограниченный batch через `FOR UPDATE SKIP LOCKED`, ставит File
`deleting` и удаляет Document. Ошибка одного элемента откатывает его savepoint,
логируется без PII и не останавливает batch.
