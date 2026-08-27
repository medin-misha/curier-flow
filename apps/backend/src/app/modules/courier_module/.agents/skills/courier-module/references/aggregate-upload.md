# Aggregate upload

`POST /courier` и `POST /courier/{id}/documents` используют один порядок:

1. полностью валидировать JSON metadata, cardinality, filename и declared
   content type;
2. создать durable `FileUploadStaging` с будущим File id/bucket/key;
3. закрыть DB-транзакцию и потоково загрузить bytes через
   `app.platform.files.MultipartUploader`;
4. durable-сохранить multipart id/result отдельными короткими транзакциями;
5. одной final transaction поглотить staging, создать ready File/Document и
   записать `FileConfirmed` в outbox;
6. в winner-ветке той же final transaction после успешного INSERT Courier
   ровно один раз записать owner-event `CourierRegistered` с topic
   `courier.registered` и всеми платформами из нормализованного request.

Любая ошибка до final commit оставляет staging как cleanup marker. UploadFile
закрывается на всех ветках. Natural-key hit ищется до staging и не вызывает
S3; повтор никогда не изменяет сохранённый Courier или детей.

Конкурентный create использует `INSERT ... ON CONFLICT DO NOTHING RETURNING`.
Проигравший не создаёт доменных детей, переводит свои staging в `deleting` и
возвращает aggregate победителя. Natural-key repeat, concurrent loser и
добавление account к существующему Courier не записывают `courier.registered`.
Email одного Courier и phone другого — 409 с `reason=identity-split`.
