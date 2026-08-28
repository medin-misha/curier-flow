# Delivery semantics

Гарантия worker — at-least-once. Собственной дедупликации по `message_id` нет:
если Telegram принял сообщение, а ACK не дошёл до RabbitMQ, redelivery и
повторный `sendMessage` допустимы.

## Матрица обработки

| Результат | Settlement и дальнейшее действие |
| --- | --- |
| Невалидный JSON, payload или AMQP envelope | `reject(requeue=False)` в main DLX/DLQ; Bot API и retry exchange не вызываются |
| Успешный `sendMessage` | ACK только после Telegram side effect |
| Network/transport error `httpx` | confirmed retry publish, затем ACK оригинала |
| Эффективный status `429` | учесть `retry_after`, confirmed retry publish, затем ACK оригинала |
| Эффективный status `5xx` или иной непредусмотренный non-success | confirmed retry publish, затем ACK оригинала |
| Эффективный status `401` | fatal error; не ACK/reject, остановить consumer и процесс |
| Любой иной эффективный `4xx` | permanent error; `reject(requeue=False)` сразу в DLQ без retry |
| Transient error при исчерпанном retry limit | `reject(requeue=False)` в DLQ без новой retry copy |
| Retry publish/return/confirm failure | fatal error; оригинал остаётся unacked |

Эффективный status берётся из Telegram JSON `error_code`, только если это
integer и не boolean; иначе используется HTTP status. Поэтому permanent
является любой код от 400 до 499, кроме отдельно обработанных `401` и `429`, в
том числе `404`. HTTP 200 с `ok != true` тоже является ошибкой и
классифицируется по тому же правилу. Сырой response и исходное transport
exception в ошибке не сохраняются.

## Retry count и delay

Header `x-retry-attempt` отсутствует на первой доставке и трактуется как `0`.
`TELEGRAM_MAX_RETRIES` имеет default `5` и допускает любое значение `>= 0`.
Transient ошибка публикует copy с attempt `+1`, пока текущий attempt меньше
limit. На attempt, равном limit, `sendMessage` ещё выполняется; только его
ошибка завершает delivery в DLQ. Таким образом, default разрешает пять retry
copies и максимум шесть вызовов `sendMessage` вместе с исходным.

Retry queue всегда держит copy 30 секунд. Для `429` worker читает
`parameters.retry_after` как неотрицательный integer; некорректное значение
становится `0`. Если `retry_after > 30`, до retry publish worker асинхронно ждёт
остаток `retry_after - 30`, после чего срабатывает queue TTL. При меньшем
значении дополнительного ожидания нет. Во время этого ожидания исходная
delivery остаётся unacked и при `prefetch=1` занимает единственный slot.

## Confirm before ACK

Retry copy публикуется `mandatory=True` через publisher-confirm channel. ACK
оригинала выполняется только после успешного возврата `publish()`, то есть
после broker confirm и без mandatory return. Любое исключение публикации
преобразуется в безопасный `RetryPublishError`; consumer помечает ошибку fatal,
закрывает channel при остановке, а RabbitMQ возвращает unacked оригинал в main
queue.

Terminal delivery не публикуется в DLQ напрямую: `reject(requeue=False)` отдаёт
её настроенному `x-dead-letter-exchange` основной очереди.
